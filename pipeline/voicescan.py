"""
Сколько разных людей говорит в банке.

На глаз это не определить: в кадре лица нет или оно другое, а голос тот же.
Скрипт измеряет высоту голоса (основную частоту) и тембр по каждому ролику
и группирует похожие. Разные женские голоса обычно расходятся на 15–25 Гц —
этого достаточно, чтобы понять, где один человек, а где два.

    python voicescan.py                 — пройти все ролики с речью
    python voicescan.py --dir clean     — только чистые

Считается на numpy автокорреляцией, без лишних библиотек.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

BANK = Path(r"C:\Ferma\factory\products\гель-дюрин\stock-reels")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
SR = 16000

# диапазон человеческого голоса: ниже — гул, выше — свист и шум
F_MIN, F_MAX = 75, 400


def read_audio(path: Path) -> np.ndarray | None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-vn", "-ac", "1", "-ar", str(SR), "-t", "60", str(wav)],
            capture_output=True,
        )
        if r.returncode != 0 or not wav.exists():
            return None
        with wave.open(str(wav), "rb") as w:
            data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return data.astype(np.float32) / 32768.0


def pitch_profile(sig: np.ndarray) -> tuple[float, float, float]:
    """
    Возвращает (медиана высоты голоса, разброс, яркость тембра).

    Высота — где человек говорит в среднем. Разброс — насколько живая
    интонация. Яркость — спектральный центроид, отличает глухой голос
    от звонкого при одинаковой высоте.
    """
    win = int(SR * 0.04)          # окно 40 мс
    hop = int(SR * 0.02)
    lo, hi = SR // F_MAX, SR // F_MIN

    f0s: list[float] = []
    centroids: list[float] = []

    for i in range(0, len(sig) - win, hop):
        frame = sig[i:i + win]
        energy = float(np.sqrt(np.mean(frame ** 2)))
        if energy < 0.02:          # тишина и паузы не считаем
            continue

        frame = frame - frame.mean()
        corr = np.correlate(frame, frame, mode="full")[win - 1:]
        if corr[0] <= 0:
            continue
        seg = corr[lo:hi]
        if seg.size == 0:
            continue
        peak = int(np.argmax(seg)) + lo
        # слабый пик = шум, а не голос
        if corr[peak] / corr[0] < 0.3:
            continue
        f0s.append(SR / peak)

        spec = np.abs(np.fft.rfft(frame * np.hanning(win)))
        freqs = np.fft.rfftfreq(win, 1 / SR)
        if spec.sum() > 0:
            centroids.append(float((spec * freqs).sum() / spec.sum()))

    if len(f0s) < 20:
        return 0.0, 0.0, 0.0
    arr = np.array(f0s)
    return float(np.median(arr)), float(np.percentile(arr, 80) - np.percentile(arr, 20)), \
        float(np.median(centroids)) if centroids else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="разные голоса в банке")
    ap.add_argument("--dir", default="", help="clean | subs; пусто — оба")
    ap.add_argument("--tol", type=float, default=9.0, help="разброс высоты в Гц внутри голоса")
    ap.add_argument("--timbre", type=float, default=180.0, help="разброс тембра в Гц внутри голоса")
    args = ap.parse_args()

    folders = [args.dir] if args.dir else ["clean", "subs", "old-clean"]
    files: list[Path] = []
    for f in folders:
        files += sorted((BANK / f).glob("*.mp4"))

    print(f"слушаю {len(files)} роликов…\n")
    rows: list[tuple[str, float, float, float]] = []

    for p in files:
        sig = read_audio(p)
        if sig is None or sig.size < SR:
            continue
        f0, spread, bright = pitch_profile(sig)
        if f0 <= 0:
            continue
        rows.append((f"{p.parent.name}/{p.name}", f0, spread, bright))

    if not rows:
        print("речь не найдена")
        return 1

    rows.sort(key=lambda r: r[1])

    # Группируем по расстоянию до центра группы, а не до соседа. По соседу
    # выходит цепочка: A близок к B, B к C, C к D — и в одной группе
    # оказываются люди, различающиеся на полсотни герц.
    #
    # Тембр — второй признак: два человека могут говорить на одной высоте,
    # но звучать по-разному, и спектральный центроид это ловит.
    groups: list[list[tuple[str, float, float, float]]] = [[rows[0]]]
    for r in rows[1:]:
        g = groups[-1]
        c_f0 = sum(x[1] for x in g) / len(g)
        c_br = sum(x[3] for x in g) / len(g)
        same_pitch = abs(r[1] - c_f0) <= args.tol
        same_timbre = abs(r[3] - c_br) <= args.timbre
        if same_pitch and same_timbre:
            g.append(r)
        else:
            groups.append([r])

    print(f"похоже на {len(groups)} разных голос(ов):\n")
    for i, g in enumerate(groups, 1):
        f0 = sum(x[1] for x in g) / len(g)
        bright = sum(x[3] for x in g) / len(g)
        kind = "низкий" if f0 < 165 else ("средний" if f0 < 210 else "высокий")
        print(f"  голос {i}: {f0:.0f} Гц ({kind}), тембр {bright:.0f} Гц, роликов {len(g)}")
        for name, hz, spread, _ in g:
            live = "живая интонация" if spread > 25 else "ровная речь"
            print(f"      {hz:5.0f} Гц  {live:<18} {name}")
        print()

    print("Голоса с разницей меньше 12 Гц могут оказаться одним человеком —")
    print("такие пары стоит послушать ушами перед клонированием.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
