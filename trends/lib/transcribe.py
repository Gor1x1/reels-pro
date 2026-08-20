r"""Расшифровка речи из ролика — для разбора референсов (шаг 4 аналитика).

    python transcribe.py <файл.mp4> [--model small]

Печатает реплики с таймкодами и пишет рядом <файл>.txt.
Работает локально на faster-whisper: бесплатно, без лимитов и без сети.

Virlo текст расшифровки не отдаёт — только метрики (число слов, язык,
качество). Поэтому дословную речь берём здесь, по скачанному файлу.
"""
import json
import os
import sys


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    if not os.path.exists(path):
        sys.exit(f"нет файла: {path}")

    size = "small"
    if "--model" in sys.argv:
        size = sys.argv[sys.argv.index("--model") + 1]

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("нет faster-whisper: python -m pip install faster-whisper")

    model = WhisperModel(size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(path, vad_filter=True)

    lines, plain = [], []
    for s in segments:
        text = s.text.strip()
        if not text:
            continue
        lines.append({"from": round(s.start, 1), "to": round(s.end, 1), "text": text})
        plain.append(f"[{s.start:5.1f}–{s.end:5.1f}] {text}")

    out = os.path.splitext(path)[0] + ".txt"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(plain))
    with open(os.path.splitext(path)[0] + ".transcript.json", "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "duration": round(info.duration, 1),
                   "segments": lines}, f, ensure_ascii=False, indent=2)

    def p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((s + "\n").encode("utf-8"))

    p(f"язык: {info.language} · длительность: {info.duration:.1f} с · реплик: {len(lines)}")
    for line in plain:
        p(line)
    p(f"\nзаписано: {out}")


if __name__ == "__main__":
    main()
