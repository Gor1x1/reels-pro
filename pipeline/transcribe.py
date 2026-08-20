"""
Расшифровка речи с пословными таймкодами — субтитры из того, что реально
сказано в кадре.

    python transcribe.py voice.wav --lang hy --out src/captions.json
    python transcribe.py clip.mp4 --lang ru --txt          — только текст

Когда нужно. В банке есть ролики с говорящей головой: там речь уже записана,
и субтитры должны совпадать с ней слово в слово. Писать их руками —
переписывать чужую речь на слух.

Про армянский честно: модель его знает хуже русского и английского, вычитывать
результат придётся. Поэтому если текст реплики известен заранее (он есть
в сценарии), субтитры надёжнее строить из сценария через `script2spec.py`,
а расшифровку использовать только там, где текста нет.

Модель качается один раз в кеш (~1.5 ГБ для large-v3, ~0.5 ГБ для medium).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# те же правила нарезки на блоки, что и в мосте от сценариста
sys.path.insert(0, str(Path(__file__).resolve().parent))


# Слова, которые модель обязана написать правильно: название бренда и термины,
# встречающиеся в роликах. Пополнять по мере появления новых товаров.
DEFAULT_HINT = {
    "hy": "Դյուրին, փիլիսոփայություն, բաղադրիչներ, անվտանգ, էկոլոգիապես մաքուր, "
          "արդյունավետություն, հայկական արտադրանք, մաքրող միջոց, հետք, լաքա, բնական",
    "ru": "Дюрин, универсальное чистящее средство, состав, экологичный, артикул, "
          "поверхности, без запаха, натуральный",
    "en": "Dyurin, universal cleaner, eco friendly, natural, stain",
}


FIX_FILE = Path(r"C:\Ferma\factory\config\fix-words.json")


def drop_final_dot(blocks: list[dict]) -> int:
    """
    Убирает точку в конце блока субтитров.

    Точка в кадре читается как «мысль закончена» и даёт зрителю повод
    смахнуть ролик. Вопросительный и восклицательный знаки оставляем —
    они, наоборот, держат.
    """
    n = 0
    for b in blocks:
        words = b.get("words") or []
        if not words:
            continue
        last = words[-1]["t"]
        stripped = last.rstrip(".։,;:")
        if stripped and stripped != last:
            words[-1]["t"] = stripped
            n += 1
    return n


def fix_words(words: list[dict], lang: str) -> int:
    """
    Заменяет слова, которые модель стабильно слышит неправильно.

    Имена и термины она пишет по звуку: «Դյուրին» превращается в «Չուրին».
    Подсказка помогает не всегда, поэтому после распознавания идёт словарь
    замен — он лежит в config/fix-words.json и пополняется по мере находок.
    """
    if not FIX_FILE.exists():
        return 0
    try:
        table = json.loads(FIX_FILE.read_text(encoding="utf-8-sig")).get(lang, {})
    except (json.JSONDecodeError, OSError):
        return 0
    if not table:
        return 0

    fixed = 0
    for w in words:
        raw = w["t"]
        # знаки препинания сохраняем: заменяем только само слово
        core = raw.strip(".,!?։՝;:«»\"'()")
        tail = raw[len(core.rstrip()):] if raw.startswith(core) else ""
        repl = table.get(core.lower())
        if repl and repl != core:
            w["t"] = repl + tail
            fixed += 1
    return fixed


def load_model(size: str):
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except (ImportError, FileNotFoundError) as e:
        print("faster-whisper не запускается:", e)
        print("нужен Microsoft Visual C++ Redistributable x64 —")
        print("  winget install Microsoft.VCRedist.2015+.x64")
        return None
    # int8 на процессоре: качество почти как float32, скорость втрое выше
    return WhisperModel(size, device="cpu", compute_type="int8")


def to_blocks(words: list[dict], lang: str) -> list[dict]:
    """Слова → блоки субтитров по тем же правилам, что и в script2spec."""
    from script2spec import MAX_CHARS, MAX_WORDS, TAIL_BAD, bare

    tail_bad = TAIL_BAD.get(lang, TAIL_BAD["ru"])
    blocks: list[dict] = []
    cur: list[dict] = []

    def flush() -> None:
        if cur:
            blocks.append({
                "start": round(cur[0]["s"], 2),
                "end": round(cur[-1]["e"], 2),
                "words": [{"t": w["t"], "s": round(w["s"], 2), "e": round(w["e"], 2)} for w in cur],
            })

    for w in words:
        # длинная пауза почти всегда совпадает с концом мысли
        gap = w["s"] - cur[-1]["e"] if cur else 0
        too_long = len(" ".join(x["t"] for x in cur + [w])) > MAX_CHARS or len(cur) + 1 > MAX_WORDS
        ends_sentence = bool(cur) and cur[-1]["t"].rstrip()[-1:] in ".!?։"

        if cur and (gap > 0.55 or ends_sentence or too_long):
            carry: list[dict] = []
            if too_long and not ends_sentence:
                while len(cur) > 2 and bare(cur[-1]["t"]) in tail_bad:
                    carry.insert(0, cur.pop())
            flush()
            cur = carry
        cur.append(w)

    flush()
    return blocks


def main() -> int:
    ap = argparse.ArgumentParser(description="расшифровка речи с таймкодами")
    ap.add_argument("src")
    ap.add_argument("--lang", default="hy", help="hy | ru | en")
    ap.add_argument("--model", default="medium", help="tiny | base | small | medium | large-v3")
    ap.add_argument("--out", help="куда записать captions.json")
    ap.add_argument("--txt", action="store_true", help="показать только текст")
    ap.add_argument("--hint", help="слова, которые модель должна писать правильно")
    ap.add_argument("--fix", metavar="CAPTIONS",
                    help="применить словарь замен к готовому captions.json и выйти")
    ap.add_argument("--no-vad", action="store_true",
                    help="выключить фильтр тишины — для плотно нарезанной речи")
    args = ap.parse_args()

    # Правка готовых субтитров словарём: дешевле, чем гонять модель заново,
    # когда ошибка нашлась уже после распознавания.
    if args.fix:
        p = Path(args.fix)
        blocks = json.loads(p.read_text(encoding="utf-8-sig"))
        total = 0
        for b in blocks:
            total += fix_words(b.get("words", []), args.lang)
            if b.get("words"):
                b["start"] = b["words"][0]["s"]
                b["end"] = b["words"][-1]["e"]
        drop_final_dot(blocks)
        p.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"исправлено слов: {total} → {p}")
        for b in blocks:
            print("  " + " ".join(w["t"] for w in b["words"]))
        return 0

    if not Path(args.src).exists():
        print(f"нет файла: {args.src}")
        return 1

    model = load_model(args.model)
    if model is None:
        return 1

    # Подсказка модели. Без неё она пишет бренд как слышит: «Դյուրին»
    # превращается в «Չուրին», а термины — в похожие по звуку слова.
    # Список слов в подсказке заметно поднимает точность на именах и терминах.
    hint = args.hint or DEFAULT_HINT.get(args.lang, "")

    print(f"слушаю {Path(args.src).name} ({args.lang}, модель {args.model})…")
    # Фильтр тишины хорош на сыром материале, но на плотно нарезанной речи
    # глотает куски: паузы там короче, чем он ждёт, и он теряет границы.
    # На смонтированном чистовике его выключают.
    segments, info = model.transcribe(
        args.src, language=args.lang, word_timestamps=True,
        initial_prompt=hint or None,
        # На плотно нарезанной речи модель, опираясь на предыдущий текст,
        # обрывается после первой фразы: следующий кусок начинается резко,
        # и она считает запись законченной. Каждый сегмент разбираем заново.
        condition_on_previous_text=False,
        no_speech_threshold=0.9,
        vad_filter=not args.no_vad,
        vad_parameters=None if args.no_vad else {"min_silence_duration_ms": 250},
    )

    words: list[dict] = []
    text_parts: list[str] = []
    for seg in segments:
        text_parts.append(seg.text.strip())
        for w in (seg.words or []):
            t = w.word.strip()
            if t:
                words.append({"t": t, "s": w.start, "e": w.end})

    fixed = fix_words(words, args.lang)
    text = " ".join(w["t"] for w in words).strip() or " ".join(text_parts).strip()

    print(f"\nдлительность речи: {info.duration:.1f} с, слов: {len(words)}")
    if fixed:
        print(f"исправлено по словарю: {fixed} слов")
    print()
    print(text or "(речь не распознана)")

    if args.txt or not args.out:
        return 0

    blocks = to_blocks(words, args.lang)
    dots = drop_final_dot(blocks)
    if dots:
        print(f"снято точек в конце блоков: {dots}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nблоков субтитров: {len(blocks)} → {args.out}")
    if args.lang == "hy":
        print("армянский распознаётся с ошибками — вычитать текст перед сборкой")
    return 0


if __name__ == "__main__":
    sys.exit(main())
