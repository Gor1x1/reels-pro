"""
Расшифровка речи с пословными таймкодами — субтитры из того, что реально
сказано в кадре.

    python transcribe.py voice.wav --lang hy --out src/captions.json
    python transcribe.py clip.mp4 --lang ru --txt          — только текст

Когда нужно. В банке есть ролики с говорящей головой: там речь уже записана,
и субтитры должны совпадать с ней слово в слово. Писать их руками —
переписывать чужую речь на слух.

Где распознаётся. В облаке ElevenLabs, модель Scribe v2 — решение владельца
17.09.2026: локальный whisper вместе с ffmpeg перегрел компьютер до мерцания
экрана. Ключ — строка ELEVENLABS_API_KEY=... в .env репозитория. В облако
уходит только звук (FLAC моно 16 кГц, несколько мегабайт). Сырой ответ
с уверенностью каждого слова ложится рядом с captions.json —
captions.elevenlabs.json. Локальный whisper заперт, см. lokalnoe_razresheno().

Про армянский честно: модели знают его хуже русского и английского, вычитывать
результат придётся. Поэтому если текст реплики известен заранее (он есть
в сценарии), субтитры надёжнее строить из сценария через `script2spec.py`,
а расшифровку использовать только там, где текста нет.
"""

from __future__ import annotations
if __name__ == "__main__":  # М-44: мимо очереди тяжёлое не идёт — перезапуск через неё
    import ochered
    ochered.v_ocheredi()

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
from pathlib import Path
if hasattr(sys.stdout, "reconfigure"):  # консоль cp1251 роняла вывод со знаками «→», «×», «≈»
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# те же правила нарезки на блоки, что и в мосте от сценариста
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
ELEVEN_URL = "https://api.elevenlabs.io/v1/speech-to-text"
ELEVEN_MODEL = "scribe_v2"
NEUVERENNO = -0.7  # logprob слова ниже — вероятность меньше половины: сверить на слух
P_NEUVERENNO = 0.5  # то же самое для локальной ветки: faster-whisper отдаёт вероятность, а не logprob

# Локальный whisper открывается только этим файлом, и кладёт его владелец.
RAZRESHENIE_LOKALNO = ROOT / "lokalnoe-raspoznavanie-razresheno.txt"


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


def lokalnoe_razresheno() -> bool:
    """
    Локальный whisper запрещён решением владельца 17.09.2026: вместе с ffmpeg он
    перегрел компьютер до мерцания экрана. Распознавание — только в облаке.
    Запрет снимает только владелец: файл RAZRESHENIE_LOKALNO кладёт он сам.
    Этой же проверкой заперты align.py и speechsplit.py.
    """
    if RAZRESHENIE_LOKALNO.exists():
        return True
    print("локальное распознавание запрещено решением владельца 17.09.2026 — только облако: "
          "transcribe.py без --engine local. Не обходить: остановись и доложи.")
    return False


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


def eleven_key() -> str:
    """Ключ ElevenLabs: из .env репозитория, потом из окружения."""
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            k, _, v = line.strip().partition("=")
            if k.strip() == "ELEVENLABS_API_KEY" and v.strip():
                return v.strip()
    return os.environ.get("ELEVENLABS_API_KEY", "").strip()


def extract_audio(src: str, dst: Path) -> bool:
    """Звук в FLAC моно 16 кГц: в облако уходят мегабайты, а не гигабайт видео."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
         "-c:a", "flac", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0 or not dst.exists():
        print("ffmpeg не вытащил звук:", (r.stderr or "").strip()[-400:])
        return False
    return True


def multipart_body(fields: list[tuple[str, str]], audio: Path) -> tuple[bytes, str]:
    """Форма multipart вручную — без лишних пакетов, как и в stock.py."""
    boundary = "reelspro" + uuid.uuid4().hex
    out: list[bytes] = []
    for k, v in fields:
        out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'
                   f"{v}\r\n".encode("utf-8"))
    out.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
               f'filename="{audio.name}"\r\nContent-Type: audio/flac\r\n\r\n'.encode("utf-8"))
    out.append(audio.read_bytes())
    out.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(out), f"multipart/form-data; boundary={boundary}"


def ask_eleven(src: str, lang: str, hint: str | None, diarize: bool) -> dict | None:
    """Один запрос к Scribe v2. Возвращает сырой ответ или None с причиной в выводе."""
    key = eleven_key()
    if not key:
        print(f"нет ключа облака: нужна строка ELEVENLABS_API_KEY=<ключ> в {ROOT / '.env'}. "
              "Ключ заводит владелец; локально не распознавать — остановись и доложи.")
        return None
    fields = [("model_id", ELEVEN_MODEL), ("language_code", lang),
              ("timestamps_granularity", "word"), ("tag_audio_events", "false"),
              ("diarize", "true" if diarize else "false")]
    # Подсказка в облаке — keyterms, она на 20% дороже: только по явному --hint.
    for term in (hint or "").split(","):
        term = " ".join(term.split()[:5])[:49]  # у облака предел: 5 слов и меньше 50 знаков
        if term:
            fields.append(("keyterms", term))
    with tempfile.TemporaryDirectory(prefix="stt-") as tmp:
        audio = Path(tmp) / "zvuk.flac"
        if not extract_audio(src, audio):
            return None
        body, ctype = multipart_body(fields, audio)
    req = urllib.request.Request(ELEVEN_URL, data=body, method="POST",
                                 headers={"xi-api-key": key, "Content-Type": ctype})
    print(f"слушаю {Path(src).name} в облаке ({lang}, ElevenLabs {ELEVEN_MODEL}, "
          f"звук {len(body) / 1e6:.1f} МБ)…")
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"облако ответило {e.code}: {e.read().decode('utf-8', errors='replace')[:600]}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print("облако недоступно:", e)
    return None


def words_from_eleven(data: dict) -> list[dict]:
    """Ответ Scribe → слова как у локальной ветки; пробелы и звуковые события — мимо."""
    words: list[dict] = []
    for w in data.get("words") or []:
        t = (w.get("text") or "").strip()
        if w.get("type") == "word" and t:
            words.append({"t": t, "s": float(w["start"]), "e": float(w["end"])})
    return words


def transcribe_eleven(args) -> tuple[list[dict], float, str] | None:
    """Облако: сырой ответ рядом с captions.json, слова — в формате локальной ветки."""
    if args.model != "medium":
        print(f"--model {args.model} относится к локальной модели; в облаке работает {ELEVEN_MODEL}")
    data = ask_eleven(args.src, args.lang, args.hint, args.diarize)
    if data is None:
        return None
    raw = Path(args.raw) if args.raw else (
        Path(args.out).with_suffix(".elevenlabs.json") if args.out else None)
    if raw:
        raw.parent.mkdir(parents=True, exist_ok=True)
        raw.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"сырой ответ облака: {raw}")
    words = words_from_eleven(data)
    shaky = [w for w in data.get("words") or []
             if w.get("type") == "word" and (w.get("logprob") or 0.0) < NEUVERENNO]
    if shaky:
        print(f"неуверенных слов: {len(shaky)} (вероятность ниже половины) — "
              "сверить по сырому ответу и на слух")
    duration = words[-1]["e"] if words else 0.0
    return words, duration, (data.get("text") or "").strip()


def transcribe_local(args) -> tuple[list[dict], float, str] | None:
    """Whisper на процессоре — только с разрешения владельца."""
    if not lokalnoe_razresheno():
        return None
    model = load_model(args.model)
    if model is None:
        return None

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
                words.append({"t": t, "s": w.start, "e": w.end, "p": round(w.probability, 2)})
    shaky = [w for w in words if w["p"] < P_NEUVERENNO]
    if shaky:
        print(f"неуверенных слов: {len(shaky)} (вероятность ниже половины) — "
              "сверить по captions.json и на слух")
    return words, info.duration, " ".join(text_parts).strip()


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
    # 17.09.2026 ~20:40 владелец вернул локальный whisper: у облака на видео 10 сломано время слов.
    ap.add_argument("--engine", default="local", choices=("elevenlabs", "local"),
                    help="local — whisper на процессоре через очередь (по умолчанию, решение владельца "
                         "17.09 20:40); elevenlabs — облако, время слов на армянском ломается")
    ap.add_argument("--model", default="medium",
                    help="только для --engine local: tiny | base | small | medium | large-v3")
    ap.add_argument("--out", help="куда записать captions.json")
    ap.add_argument("--txt", action="store_true", help="показать только текст")
    ap.add_argument("--hint", help="слова, которые модель должна писать правильно; "
                                   "в облаке — через запятую и на 20% дороже")
    ap.add_argument("--fix", metavar="CAPTIONS",
                    help="применить словарь замен к готовому captions.json и выйти")
    ap.add_argument("--no-vad", action="store_true",
                    help="только local: выключить фильтр тишины — для плотно нарезанной речи")
    ap.add_argument("--diarize", action="store_true",
                    help="облако: разметить говорящих — когда в записи слышна подсказка")
    ap.add_argument("--raw", help="облако: куда положить сырой ответ (по умолчанию рядом с --out)")
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

    got = transcribe_local(args) if args.engine == "local" else transcribe_eleven(args)
    if got is None:
        return 1
    words, duration, text_fallback = got

    fixed = fix_words(words, args.lang)
    text = " ".join(w["t"] for w in words).strip() or text_fallback

    print(f"\nдлительность речи: {duration:.1f} с, слов: {len(words)}")
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
