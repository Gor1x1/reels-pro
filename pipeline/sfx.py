"""
Звуковые эффекты под монтаж. Синтезируются, как и музыка, — чужие библиотеки
эффектов тоже бывают лицензированы, а на восьми тысячах публикаций в месяц
это лишний риск на ровном месте.

    python sfx.py --out-dir public/sfx        — собрать весь набор
    python sfx.py --only whoosh --out w.wav

Набор намеренно короткий. Эффект на каждой склейке превращает ролик
в детскую презентацию: whoosh уместен на смене места действия, impact —
на хуке и цифре, pop — на появлении титра. Больше трёх-четырёх штук
на ролик не ставить.
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

SR = 44100


def save(samples: list[float], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    peak = max((abs(v) for v in samples), default=1.0) or 1.0
    norm = [v / peak * 0.85 for v in samples]
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32000)) for v in norm))


def whoosh(sec: float = 0.42) -> list[float]:
    """Пролёт: шум с фильтром, который едет вверх и обратно вниз."""
    n = int(sec * SR)
    rng = random.Random(1)
    out, prev = [], 0.0
    for i in range(n):
        p = i / n
        # огибающая-колокол: резкий вход, мягкий выход
        amp = math.sin(math.pi * p) ** 1.6
        raw = rng.uniform(-1, 1)
        # однополюсный фильтр: коэффициент меняется — это и даёт «пролёт»
        k = 0.02 + 0.55 * math.sin(math.pi * p)
        prev = prev + k * (raw - prev)
        out.append(prev * amp)
    return out


def impact(sec: float = 0.55) -> list[float]:
    """Удар под хук и под цифру. Низ плюс короткий щелчок сверху."""
    n = int(sec * SR)
    rng = random.Random(2)
    out = []
    for i in range(n):
        p = i / n
        f = 90 * (1 - p) ** 2 + 38
        low = math.sin(2 * math.pi * f * i / SR) * (1 - p) ** 1.8
        crack = rng.uniform(-1, 1) * (1 - p) ** 22 * 0.5
        out.append(low * 0.9 + crack)
    return out


def pop(sec: float = 0.13) -> list[float]:
    """Появление титра. Короткий тон с быстрым подъёмом частоты."""
    n = int(sec * SR)
    out = []
    for i in range(n):
        p = i / n
        f = 420 + 680 * p
        out.append(math.sin(2 * math.pi * f * i / SR) * (1 - p) ** 3.5)
    return out


def click(sec: float = 0.06) -> list[float]:
    n = int(sec * SR)
    rng = random.Random(3)
    return [rng.uniform(-1, 1) * (1 - i / n) ** 12 for i in range(n)]


def riser(sec: float = 1.1) -> list[float]:
    """Нарастание перед раскрытием — под сцену «до/после»."""
    n = int(sec * SR)
    out = []
    for i in range(n):
        p = i / n
        f = 180 * (2 ** (2.4 * p))
        v = math.sin(2 * math.pi * f * i / SR)
        v += math.sin(2 * math.pi * f * 1.5 * i / SR) * 0.35
        out.append(v * (p ** 2) * 0.8)
    return out


KIT = {
    "whoosh": (whoosh, "смена места действия, переход whip"),
    "impact": (impact, "хук, цифра, кульминация"),
    "pop": (pop, "появление титра или плашки"),
    "click": (click, "мелкий акцент, шаг инструкции"),
    "riser": (riser, "нарастание перед раскрытием"),
}


def to_mp3(src: Path) -> bool:
    ff = shutil.which("ffmpeg")
    if not ff:
        return False
    dst = src.with_suffix(".mp3")
    r = subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-c:a", "libmp3lame", "-b:a", "192k", str(dst)],
        capture_output=True,
    )
    if r.returncode == 0:
        src.unlink()
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="набор звуковых эффектов")
    ap.add_argument("--out-dir", default="public/sfx")
    ap.add_argument("--only", choices=list(KIT))
    ap.add_argument("--out", help="файл, если собирается один эффект")
    args = ap.parse_args()

    if args.only:
        path = Path(args.out or f"{args.only}.wav")
        save(KIT[args.only][0](), path)
        if path.suffix == ".wav":
            to_mp3(path)
        print(f"готово: {path.with_suffix('.mp3')}")
        return 0

    d = Path(args.out_dir)
    print(f"собираю набор в {d}:")
    for name, (fn, desc) in KIT.items():
        p = d / f"{name}.wav"
        save(fn(), p)
        to_mp3(p)
        print(f"  {name}.mp3 — {desc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
