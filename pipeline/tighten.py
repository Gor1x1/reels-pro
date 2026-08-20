"""
Убрать из говорящей головы паузы, тишину и лишние подходы.

Отдельная задача от `speechsplit.py`. Тот делит **голоса** — автора и
подсказку из динамика. Здесь голос один, но между фразами человек молчит:
слушает подсказку в наушнике, собирается с мыслями, начинает дубль заново.
В записи это полная тишина по 4–5 секунд.

    python tighten.py raw.mp4 --plan runs/plan.json      посмотреть, что нашлось
    python tighten.py raw.mp4 --out runs/clean.mp4       собрать чистовик
    python tighten.py raw.mp4 --out c.mp4 --drop 63.3-70.5 --drop 71.5-78.5

Порог тишины здесь **абсолютный**, а не «на N дБ тише пика». Относительный
порог срезает тихие концы фраз: у живой речи окончание проседает на 15–20 дБ
от середины, и по такому порогу оно неотличимо от паузы.

Куски склеиваются с перекодированием: резка по ключевым кадрам промахивается
на десятые доли секунды, а на речи это слышно как щелчок.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

SR = 16000
WIN = 0.05           # шаг анализа
SILENCE_DB = -50.0   # тише этого — тишина, а не тихая речь
MIN_PAUSE = 0.45     # паузу короче не трогаем: это дыхание внутри фразы
MIN_SPEECH = 0.35    # островок речи короче — щелчок или вдох
AIR = 0.18           # воздух вокруг куска, чтобы не срезать согласные


def duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def audio(path: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-ac", "1", "-ar", str(SR), str(wav)], check=True)
        with wave.open(str(wav), "rb") as w:
            raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def speech_spans(sig: np.ndarray, silence_db: float,
                 min_pause: float = MIN_PAUSE) -> list[tuple[float, float]]:
    step = int(SR * WIN)
    n = len(sig) // step
    db = np.full(n, -99.0, dtype=np.float32)
    for i in range(n):
        f = sig[i * step:(i + 1) * step]
        rms = float(np.sqrt(np.mean(f ** 2))) if f.size else 0.0
        if rms > 1e-7:
            db[i] = 20 * np.log10(rms)

    on = db > silence_db

    # затянуть короткие провалы: внутри фразы есть смычки согласных и вдохи
    fill = int(min_pause / WIN)
    i = 0
    while i < len(on):
        if not on[i]:
            j = i
            while j < len(on) and not on[j]:
                j += 1
            if 0 < i and j < len(on) and (j - i) < fill:
                on[i:j] = True
            i = j
        else:
            i += 1

    spans: list[tuple[float, float]] = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            a, b = i * WIN, j * WIN
            if b - a >= MIN_SPEECH:
                spans.append((max(0.0, a - AIR), b + AIR))
            i = j
        else:
            i += 1

    # после добавления воздуха соседние куски могут перекрыться — сводим
    merged: list[tuple[float, float]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return merged


def parse_drop(items: list[str]) -> list[tuple[float, float]]:
    out = []
    for it in items or []:
        try:
            a, b = it.split("-", 1)
            out.append((float(a), float(b)))
        except ValueError:
            sys.stderr.write(f"не понял интервал: {it} (нужно 12.3-18.9)\n")
    return out


def cut(src: Path, spans: list[tuple[float, float]], out: Path) -> bool:
    """Вырезать куски и склеить. Перекодирование — иначе щелчки на стыках."""
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, (a, b) in enumerate(spans):
            p = Path(tmp) / f"p{i:03d}.mp4"
            r = subprocess.run(
                [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                 "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                 "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                 "-avoid_negative_ts", "make_zero", str(p)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                sys.stderr.write((r.stderr or "")[-500:])
                return False
            parts.append(p)

        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.stderr.write((r.stderr or "")[-500:])
            return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="убрать паузы и лишние подходы")
    ap.add_argument("src")
    ap.add_argument("--out", help="куда собрать чистовик")
    ap.add_argument("--plan", help="куда записать план нарезки")
    ap.add_argument("--drop", action="append", default=[],
                    help="выбросить интервал исходника, например 63.3-70.5")
    ap.add_argument("--take", action="append", default=[],
                    help="взять только эти интервалы, в этом порядке; "
                         "паузы внутри них всё равно вычищаются")
    ap.add_argument("--silence", type=float, default=SILENCE_DB,
                    help="порог тишины в дБ")
    ap.add_argument("--min-pause", type=float, default=0.75,
                    help="паузу короче этого не трогаем — это дыхание в речи")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"нет файла: {src}")
        return 1

    total = duration(src)
    spans = speech_spans(audio(src), args.silence, args.min_pause)
    if not spans:
        print("речь не найдена — проверь порог тишины")
        return 1

    takes = parse_drop(args.take)
    if takes:
        # Явно заданные куски: границы уважаем как есть — они выставлены по
        # смыслу, а не по тишине. Внутри каждого вычищаем длинные паузы,
        # обрезая найденную речь по краям интервала.
        keep = []
        for ta, tb in takes:
            inner = [(max(a, ta), min(b, tb)) for a, b in spans
                     if b > ta and a < tb]
            keep.extend([(a, b) for a, b in inner if b - a > 0.2])
    else:
        drops = parse_drop(args.drop)
        keep = []
        for a, b in spans:
            # выбрасываем куски, попавшие в заданные интервалы больше чем наполовину
            mid = (a + b) / 2
            if any(da <= mid <= db for da, db in drops):
                continue
            keep.append((a, b))

    kept = sum(b - a for a, b in keep)
    print(f"исходник {total:.1f} с, речи {kept:.1f} с, "
          f"убрано {total - kept:.1f} с ({(total - kept) / total * 100:.0f}%)")
    print(f"кусков: {len(keep)}")
    for i, (a, b) in enumerate(keep, 1):
        print(f"  {i:2d}. {a:6.2f} → {b:6.2f}   {b - a:5.2f} с")

    if args.plan:
        Path(args.plan).parent.mkdir(parents=True, exist_ok=True)
        Path(args.plan).write_text(
            json.dumps([{"start": round(a, 2), "end": round(b, 2)} for a, b in keep],
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"план: {args.plan}")

    if args.out:
        if not cut(src, keep, Path(args.out)):
            return 1
        print(f"чистовик: {args.out}  ({duration(Path(args.out)):.1f} с)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
