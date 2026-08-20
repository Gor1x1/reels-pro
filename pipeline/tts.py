"""
Синтез речи на армянском — локально, без ключей и подписок.

Голос `hy_AM-gor-medium` (Piper, ONNX) — восточноармянский, тот самый
диалект, на котором говорит Армения. Работает на процессоре, весит 64 МБ,
секунда речи считается быстрее, чем звучит.

    python tts.py --text "Իսկ դու հավատու՞մ ես" --out voice.wav
    python tts.py --file text.md --out voice.wav --speed 1.05

Что это НЕ заменяет: голоса семи личностей. Те клонируются с образцов
креаторов и звучат как живые люди. Этот — служебный: проверить текст,
собрать черновик, озвучить закадровый кусок.

Длинный текст режется по предложениям и склеивается: модель на длинном
куске начинает тараторить и глотает паузы, на которых держится ирония.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

VOICE = Path(r"C:\Ferma\factory\assets\tts\hy_AM-gor-medium.onnx")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Пауза между предложениями. Без неё фразы слипаются в простыню.
GAP_SEC = 0.30
# После вопроса держим дольше — зритель должен успеть ответить про себя.
GAP_QUESTION = 0.55


def for_speech(s: str) -> str:
    """Армянская пунктуация → та, что понимает espeak.

    Вопросительный знак ՞ в армянском стоит над ударной гласной внутри
    слова. espeak его не читает как вопрос и произносит фразу ровно,
    поэтому переносим вопрос в конец обычным «?».
    """
    q = "՞" in s
    s = s.replace("՞", "").replace("՜", "").replace("՛", "")
    s = s.replace("՝", ", ").replace("։", ". ")
    s = re.sub(r"\s+", " ", s).strip(" .,")
    return s + ("?" if q else ".")


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[։.!?])\s+|\n+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def synth(pieces: list[str], out: Path, speed: float, model: Path) -> list[dict] | None:
    """Синтез. Возвращает границы каждой фразы — они известны точно."""
    try:
        import numpy as np
        from piper import PiperVoice
    except ImportError as e:
        print("не хватает библиотек:", e)
        print("  python -m pip install piper-tts")
        return None

    if not model.exists():
        print(f"нет модели: {model}")
        print("  скачать: davit312/piper-TTS-Armenian → v3/hy_AM-gor-medium.onnx")
        return None

    voice = PiperVoice.load(str(model), config_path=str(model) + ".json")
    rate = int(voice.config.sample_rate)
    chunks: list[np.ndarray] = []
    spans: list[dict] = []
    cursor = 0.0

    for i, raw_line in enumerate(pieces, 1):
        line = for_speech(raw_line)
        parts = [c.audio_float_array for c in voice.synthesize(line)]
        audio = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
        chunks.append(audio)
        dur = len(audio) / rate
        spans.append({"text": raw_line, "start": round(cursor, 3),
                      "end": round(cursor + dur, 3)})
        gap = GAP_QUESTION if line.endswith("?") else GAP_SEC
        chunks.append(np.zeros(int(rate * gap), dtype=np.float32))
        cursor += dur + gap
        print(f"  {i}/{len(pieces)}  {dur:5.1f} с   {raw_line[:46]}")

    audio = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio / peak * 0.9

    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "raw.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((audio * 32000).astype("<i2").tobytes())

        out.parent.mkdir(parents=True, exist_ok=True)
        # Синтез звучит суховато и плоско: подрезаем гул, слегка поднимаем
        # присутствие голоса, дальше обычная нормализация под ролик.
        af = ("highpass=f=90,equalizer=f=3000:t=q:w=1.4:g=3,"
              "acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
              "loudnorm=I=-16:TP=-1.5:LRA=11")
        if abs(speed - 1.0) > 0.01:
            af = f"atempo={speed:.3f}," + af
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw),
             "-af", af, "-ar", "48000", "-ac", "1", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            sys.stderr.write((r.stderr or "")[-800:])
            return None

    # atempo сжал дорожку — границы фраз сдвигаются вместе с ней
    if abs(speed - 1.0) > 0.01:
        for sp in spans:
            sp["start"] = round(sp["start"] / speed, 3)
            sp["end"] = round(sp["end"] / speed, 3)
    return spans


def captions_from_spans(spans: list[dict], lang: str) -> list[dict]:
    """
    Субтитры из границ фраз.

    Тайминги здесь честнее выравнивания: синтезатор произносил каждую фразу
    отдельно и знает её длину до миллисекунды. Внутри фразы слова
    раскладываются по длине — читается это ровно, а границу предложения
    блок не перепрыгивает.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from script2spec import split_line  # noqa: PLC0415

    out: list[dict] = []
    for sp in spans:
        blocks = split_line(sp["text"], lang) or [sp["text"].split()]
        total = sum(len(w) + 1 for b in blocks for w in b) or 1
        span = max(sp["end"] - sp["start"], 0.1)
        t = sp["start"]
        for block in blocks:
            words = []
            for w in block:
                dur = span * (len(w) + 1) / total
                words.append({"t": w, "s": round(t, 2), "e": round(t + dur, 2)})
                t += dur
            out.append({"start": words[0]["s"], "end": words[-1]["e"],
                        "words": words})
    return out


def read_text(path: str) -> str:
    raw = Path(path).read_text(encoding="utf-8-sig")
    # В наших текстовках реплики лежат внутри блока ```…```, а вокруг —
    # разбор приёмов и заметки. Озвучивать надо только блок.
    fenced = re.findall(r"```[a-z]*\n(.*?)```", raw, re.S)
    if fenced:
        return max(fenced, key=len).strip()
    lines = [l for l in raw.splitlines()
             if l.strip() and not l.lstrip().startswith(("#", "|", "-", "`", ">", "*"))]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="синтез армянской речи локально")
    ap.add_argument("--text", help="текст одной строкой")
    ap.add_argument("--file", help="файл с текстом (txt или md)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--speed", type=float, default=1.0, help="темп речи, до 1.3")
    ap.add_argument("--model", default=str(VOICE))
    ap.add_argument("--captions", help="куда записать субтитры с таймингами")
    ap.add_argument("--lang", default="hy")
    args = ap.parse_args()

    text = read_text(args.file) if args.file else (args.text or "")
    if not text.strip():
        print("нужен --text или --file")
        return 1

    pieces = split_sentences(text)
    print(f"предложений: {len(pieces)}")
    spans = synth(pieces, Path(args.out), args.speed, Path(args.model))
    if spans is None:
        return 1

    if args.captions:
        import json  # noqa: PLC0415
        blocks = captions_from_spans(spans, args.lang)
        p = Path(args.captions)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(blocks, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"субтитров: {len(blocks)} блоков → {p}")

    dur = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", args.out],
        capture_output=True, text=True,
    ).stdout.strip()
    print(f"\nготово: {args.out}  ({float(dur or 0):.1f} с)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
