#!/usr/bin/env python3
"""
Дыры в маске человека по всему ролику — замером, а не глазами.

Дыра — замкнутый внутри силуэта провал маски там, где кадр не цвета стены: сквозь
неё на новом фоне светит фон. На рилсе 1 такие дыры шли в 446 кадрах из 880, на
пробных кадрах их не было, а в ролике они мигали «бликами» на груди.

  python maska_dyry.py --video chistovik.mp4 --alpha alpha.mkv --plate-cache plate.npz

Код выхода 0 — дыр нет; 2 — есть (список отрезков в выводе). fon_compose.py с
--video и --plate-cache такие дыры закрывает сам; этот замер — для проверки маски
до сборки и после неё.
"""
import argparse, subprocess, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matte_core import probe, reader, read_frame, PlateTracker, repair_holes

p = argparse.ArgumentParser()
p.add_argument("--video", required=True, help="чистовик, по которому считалась маска")
p.add_argument("--alpha", required=True, help="маска из matte.py --alpha-out")
p.add_argument("--plate-cache", required=True, help="подложка стены из matte.py")
p.add_argument("--min-px", type=int, default=200, help="дыра меньше — не считается")
a = p.parse_args()

W, H, fps, _ = probe(a.video)
rd = reader(a.video, W, H)
ra = subprocess.Popen(f'ffmpeg -v error -i "{a.alpha}" -f rawvideo -pix_fmt gray -',
                      shell=True, stdout=subprocess.PIPE, bufsize=W * H * 4)
z = np.load(a.plate_cache)
tr = PlateTracker({"plate": z["plate"], "seen": z["seen"], "conf": z["conf"], "q": int(z["q"])}, W, H)
bad = []
n = 0
while True:
    I = read_frame(rd, W, H)
    raw = ra.stdout.read(W * H)
    if I is None or len(raw) < W * H:
        break
    al = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32) / 255.0
    _, fixed = repair_holes(I, al, tr.frame(I, al))
    if fixed > a.min_px:
        bad.append((n, fixed))
    n += 1
rd.kill()
ra.kill()

print(f"кадров {n}, с дырами больше {a.min_px} px: {len(bad)}")
if not bad:
    sys.exit(0)
runs, start, prev = [], bad[0][0], bad[0][0]
for f, _ in bad[1:]:
    if f != prev + 1:
        runs.append((start, prev))
        start = f
    prev = f
runs.append((start, prev))
print("отрезки, с:", ", ".join(f"{s / fps:.1f}-{e / fps:.1f}" for s, e in runs))
worst = max(bad, key=lambda x: x[1])
print(f"самая большая дыра: кадр {worst[0]} ({worst[0] / fps:.1f} с), {worst[1]} px")
sys.exit(2)
