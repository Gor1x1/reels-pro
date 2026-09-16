#!/usr/bin/env python3
"""
Подстановка фона под готовый слой человека — без повторной вырезки.

matte.py один раз вырезает человека (--fg-out слой, --alpha-out маска). Дальше фон
меняется за минуты: так работают в профессиональном монтаже — ключ отдельно, фон
отдельно. Здесь же то, что прячет вырезку от глаза:

  свет фона на кромке (light wrap);
  фон в расфокусе и по яркости/теплоте под человека;
  одинаковое зерно на фоне и на человеке — чистый размытый фон за шумной съёмкой
  с телефона читается как наклейка;
  лёгкое затемнение краёв кадра — взгляд идёт к лицу.

  python fon_compose.py --video chistovik.mp4 --alpha alpha.mkv --plate-cache plate.npz --bg fon.mp4 --out talk.mp4
  python fon_compose.py ... --still 5.0 --out proba.png          # один кадр для сравнения фонов

С --video край пересобирается здесь же: подрезка маски и цвет края по подложке стены.
Нейросеть второй раз не нужна — правка кромки занимает минуты, а не двадцать.
"""
import argparse, subprocess, sys, time
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matte_core import probe, reader, read_frame, Background, PlateTracker, foreground_colors, choke

p = argparse.ArgumentParser()
src = p.add_mutually_exclusive_group(required=True)
src.add_argument("--video", help="чистовик, по которому считалась маска (со звуком): край пересобирается")
src.add_argument("--fg", help="готовый слой человека из matte.py --fg-out (цвет, умноженный на маску)")
p.add_argument("--plate-cache", default="", help="подложка стены из matte.py: точнее цвет края")
p.add_argument("--choke", type=int, default=1, help="подрезать маску внутрь, px (только с --video)")
p.add_argument("--edge-soft", type=float, default=0.6, help="мягкость кромки, px (только с --video)")
p.add_argument("--alpha", required=True, help="маска из matte.py --alpha-out")
p.add_argument("--bg", required=True, help="картинка или видео фона")
p.add_argument("--out", required=True)
p.add_argument("--from", dest="t0", type=float, default=None)
p.add_argument("--to", dest="t1", type=float, default=None)
p.add_argument("--still", type=float, default=None, help="собрать один кадр на этой секунде (PNG)")
# фон
p.add_argument("--bg-from", type=float, default=0.0, help="с какой секунды фона начинать")
p.add_argument("--bg-blur", type=float, default=10.0, help="расфокус фона, sigma px (0 — резкий)")
p.add_argument("--bg-slow", type=float, default=1.0)
p.add_argument("--bg-zoom", type=float, default=1.0)
p.add_argument("--bg-dx", type=int, default=0)
p.add_argument("--bg-push", type=float, default=0.04)
p.add_argument("--bg-bright", type=float, default=1.0, help="яркость фона")
p.add_argument("--bg-warm", type=float, default=0.0, help="-1..1: холоднее / теплее")
p.add_argument("--bg-sat", type=float, default=1.0, help="насыщенность фона")
p.add_argument("--vignette", type=float, default=0.25, help="0..1 затемнение краёв кадра")
# человек
p.add_argument("--exposure", type=float, default=1.0)
p.add_argument("--grade", default="1.0,1.0,1.0")
p.add_argument("--head", default="", help="x,y,w,h лица: центр света для --relight")
p.add_argument("--relight", type=float, default=0.0)
p.add_argument("--lightwrap", type=float, default=0.25)
p.add_argument("--grain", type=float, default=0.012, help="зерно на весь кадр, СКО в долях яркости")
p.add_argument("--quiet", action="store_true")
a = p.parse_args()


def log(*x):
    if not a.quiet:
        print(*x, flush=True)


SRC = a.video or a.fg
W, H, FPS, dur = probe(SRC)
t0 = a.still if a.still is not None else (a.t0 or 0.0)
t1 = t0 + 1.0 / FPS if a.still is not None else (min(a.t1, dur) if a.t1 else dur)
N = max(1, int(round((t1 - t0) * FPS)))

# фон: для кадра-пробы начинаем с той же секунды фона, что и в ролике
bg_start = a.bg_from + (t0 if a.still is not None or a.t0 else 0.0)
BG = Background(a.bg, W, H, N + int(bg_start * FPS), fps=FPS, blur=a.bg_blur, slow=a.bg_slow,
                zoom=a.bg_zoom, dx=a.bg_dx, push=a.bg_push, log=log)
for _ in range(int(bg_start * FPS)):
    BG.next()

# цвет фона
M = np.eye(3, dtype=np.float32)
if a.bg_warm:
    k = 0.12 * a.bg_warm
    M = np.diag([1 + k, 1 + k * 0.25, 1 - k]).astype(np.float32)
lum_w = np.array([0.2126, 0.7152, 0.0722], np.float32)

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = None
if a.vignette > 0:
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.42) / (H * 0.62)) ** 2)
    VIG = (1 - a.vignette * np.clip(r - 0.35, 0, 1) ** 1.6).astype(np.float32)[..., None]
LIGHT = None
if a.relight > 0:
    fy = float(a.head.split(",")[1]) if a.head else 0.35
    ramp = np.clip((yy[:, :1] - fy * H) / ((1.0 - fy) * H), 0, 1)
    LIGHT = (1.0 - a.relight * ramp ** 1.2)[..., None] * np.ones((1, W, 1), np.float32)
gr = np.array([float(x) for x in a.grade.split(",")], np.float32).reshape(1, 1, 3) * a.exposure
rng = np.random.default_rng(7)

tracker = None
if a.video and a.plate_cache:
    z = np.load(a.plate_cache)
    tracker = PlateTracker({"plate": z["plate"], "seen": z["seen"], "conf": z["conf"], "q": int(z["q"])}, W, H)
rf = reader(SRC, W, H, ss=t0 if t0 else None, to=t1 if (a.t1 or a.still is not None) else None)
ra = subprocess.Popen(
    f'ffmpeg -v error {"-ss " + str(t0) + " " if t0 else ""}-i "{a.alpha}" '
    f'{"-t " + str(t1 - t0) + " " if (a.t1 or a.still is not None) else ""}-f rawvideo -pix_fmt gray -',
    shell=True, stdout=subprocess.PIPE, bufsize=W * H * 4)

wr = None
if a.still is None:
    ss_a = f"-ss {t0} " if t0 else ""
    to_a = f"-t {t1 - t0} " if a.t1 else ""
    wr = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {ss_a}{to_a}-i "{SRC}" '
        f'-map 0:v -map 1:a? -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -c:a aac -b:a 256k -shortest "{a.out}" -y',
        shell=True, stdin=subprocess.PIPE)

started = time.time()
n = 0
while n < N:
    fgp = read_frame(rf, W, H)
    raw = ra.stdout.read(W * H)
    if fgp is None or len(raw) < W * H:
        break
    al = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32) / 255.0
    if a.video:
        # край из исходника: подрезка маски и очищенный от стены цвет
        I = fgp
        Bp = tracker.frame(I, al) if tracker else None
        al = choke(al, a.choke, a.edge_soft)
        fgp = foreground_colors(I, al, plate=Bp) * al[..., None]
    bg = BG.next()
    if a.bg_warm:
        bg = bg @ M.T
    if a.bg_sat != 1.0:
        l = (bg @ lum_w)[..., None]
        bg = l + (bg - l) * a.bg_sat
    bg = np.clip(bg * a.bg_bright, 0, 1)
    if VIG is not None:
        bg = bg * VIG

    fgp = fgp * gr
    if LIGHT is not None:
        fgp = fgp * LIGHT
    if a.lightwrap > 0:
        small = cv2.resize(bg, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        bgb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (W, H), interpolation=cv2.INTER_LINEAR)
        inv = cv2.GaussianBlur(1.0 - al, (0, 0), 5)
        lw = (np.clip(inv * al * 2.0, 0, 1) * a.lightwrap)[..., None]
        fgp = fgp * (1 - lw) + bgb * lw * al[..., None]
    comp = fgp + bg * (1 - al)[..., None]
    if a.grain > 0:
        g = rng.standard_normal((H // 2, W // 2), dtype=np.float32) * a.grain
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
        # зерно сильнее в средних тонах, как у сенсора
        comp = comp + g * (0.5 + 0.5 * (1 - np.abs(comp * 2 - 1)))
    out8 = cv2.convertScaleAbs(np.clip(comp, 0, 1), alpha=255.0)
    if a.still is not None:
        cv2.imwrite(a.out, cv2.cvtColor(out8, cv2.COLOR_RGB2BGR))
        n += 1
        break
    wr.stdin.write(out8.tobytes())
    n += 1
    if n % 90 == 0:
        el = time.time() - started
        log(f"  кадр {n}/{N}  {el / n:.2f} с/кадр")

rf.kill()
ra.kill()
BG.close()
if wr:
    wr.stdin.close()
    wr.wait()
log(f"готово: {n} кадров за {(time.time() - started):.0f} с → {a.out}")
