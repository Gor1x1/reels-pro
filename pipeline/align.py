"""
Выравнивание известного текста по звуку — точные тайминги без распознавания.

Задача не «расшифровать», а «узнать, когда что было сказано». Текст реплик
у нас уже есть — он написан в сценарии носителем языка. Распознавание на
армянском ошибается в каждом четвёртом слове, и эти ошибки уходят прямо
в субтитры.

Решение: берём у модели только **тайминги**, а слова подставляем свои.
Модель может услышать «Չուրին» вместо «Դյուրին» — неважно, нам от неё нужно
лишь «здесь говорили с 2.4 по 3.1 секунду».

    python align.py voice.wav --text "Այս հետքը չի գնում։" --lang hy --out src/captions.json
    python align.py clip.mp4 --script script.json --out src/captions.json

Со `--script` текст берётся из реплик сценария, а тайминги раскладываются
по битам: так субтитры совпадают и со звуком, и с монтажом.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from script2spec import MAX_CHARS, MAX_WORDS, READ_CPS, split_line  # noqa: E402


def speech_segments(src: str, lang: str, model_size: str) -> list[dict]:
    """
    Отрезки речи с таймингами. Слова из модели не используем — только границы.
    """
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except (ImportError, FileNotFoundError) as e:
        print("faster-whisper не запускается:", e)
        return []

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        src, language=lang, word_timestamps=True,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 350},
    )

    out: list[dict] = []
    for seg in segments:
        words = [
            {"s": w.start, "e": w.end}
            for w in (seg.words or [])
            if w.word.strip()
        ]
        if words:
            out.append({"start": seg.start, "end": seg.end, "n": len(words), "words": words})
    return out


def spread(words: list[str], slots: list[dict]) -> list[dict]:
    """
    Раскладывает наши слова по чужим таймингам.

    Слов у нас и «слов» у модели обычно разное количество: она делит речь
    по-своему. Поэтому идём не по словам, а по времени: каждому нашему слову
    достаётся кусок пропорционально его длине в буквах.
    """
    if not slots:
        return []

    speech_start = slots[0]["start"]
    speech_end = slots[-1]["end"]
    total = max(speech_end - speech_start, 0.3)
    chars = sum(len(w) for w in words) or 1

    # паузы между отрезками речи не отдаём под слова — иначе субтитр
    # повиснет там, где человек молчит
    voiced = [(s["start"], s["end"]) for s in slots]
    voiced_total = sum(e - s for s, e in voiced) or total

    out: list[dict] = []
    pos = 0.0  # сколько «озвученного» времени уже роздано

    def at(offset: float) -> float:
        """Переводит позицию внутри озвученного времени в реальное время."""
        left = offset
        for s, e in voiced:
            span = e - s
            if left <= span:
                return s + left
            left -= span
        return speech_end

    for w in words:
        share = voiced_total * len(w) / chars
        out.append({"t": w, "s": round(at(pos), 2), "e": round(at(pos + share), 2)})
        pos += share

    return out


def to_blocks(timed: list[dict], lang: str) -> list[dict]:
    """Слова с таймингами → блоки субтитров по границам смысла."""
    text = " ".join(w["t"] for w in timed)
    groups = split_line(text, lang)

    blocks: list[dict] = []
    i = 0
    for g in groups:
        take = timed[i:i + len(g)]
        if not take:
            break
        blocks.append({
            "start": take[0]["s"],
            "end": take[-1]["e"],
            "words": take,
        })
        i += len(g)
    return blocks


def main() -> int:
    ap = argparse.ArgumentParser(description="выравнивание текста по звуку")
    ap.add_argument("src", help="аудио или видео с речью")
    ap.add_argument("--text", help="текст реплики")
    ap.add_argument("--script", help="сценарий: текст берётся из реплик битов")
    ap.add_argument("--lang", default="hy")
    ap.add_argument("--model", default="small", help="для таймингов хватает small")
    ap.add_argument("--out", help="куда записать captions.json")
    args = ap.parse_args()

    if args.script:
        script = json.loads(Path(args.script).read_text(encoding="utf-8-sig"))
        text = " ".join((b.get("line") or "").strip() for b in script.get("beats", []) if b.get("line"))
        lang = script.get("lang", args.lang)
    else:
        text = (args.text or "").strip()
        lang = args.lang

    if not text:
        print("нужен --text или --script с репликами")
        return 1

    words = [w for w in text.split() if w]
    print(f"текст: {len(words)} слов")

    slots = speech_segments(args.src, lang, args.model)
    if not slots:
        print("речь не найдена — тайминги взять неоткуда")
        return 1

    heard = sum(s["n"] for s in slots)
    print(f"речь: {slots[0]['start']:.1f}–{slots[-1]['end']:.1f} с, "
          f"отрезков {len(slots)}, модель услышала {heard} слов")
    if abs(heard - len(words)) > max(len(words) * 0.4, 3):
        print("  внимание: счёт слов сильно расходится — проверь, тот ли это текст")

    timed = spread(words, slots)
    blocks = to_blocks(timed, lang)

    # скорость чтения: блок не должен мелькать
    for i, b in enumerate(blocks, 1):
        chars = len(" ".join(w["t"] for w in b["words"]))
        span = b["end"] - b["start"]
        if span < chars / READ_CPS - 0.3:
            print(f"  блок {i}: {span:.1f} с на {chars} знаков — говорят быстро, "
                  f"текст может не успеть прочитаться")

    print(f"\nблоков субтитров: {len(blocks)}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"записано: {args.out}")
        print("текст свой, тайминги от звука — распознавание в субтитры не попадает")
    else:
        for b in blocks:
            print(f"  {b['start']:6.2f}–{b['end']:6.2f}  {' '.join(w['t'] for w in b['words'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
