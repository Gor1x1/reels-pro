#!/usr/bin/env python3
"""
Замена фона в видео — вторая версия (16.09.2026).

Нейросеть RobustVideoMatting даёт грубую маску человека. Дальше — приёмы кеинг-программ
(matte_core.py), без них на стене цвета кожи получались ореол, рваный край и мерцание:

  1. чистая подложка стены из всего ролика (clean plate);
  2. ключ по известному фону: край там, где кадр перестаёт быть стеной;
  3. подавление дрожи маски во времени по оптическому потоку;
  4. очистка цвета края без деления на альфу;
  5. фон без рывка петли, с правильной частотой кадров, с глубиной резкости.

БЕЗОПАСНОЕ КАДРИРОВАНИЕ осталось: если человек обрезан краем исходника, уменьшать
его нельзя — срез уедет внутрь кадра. Режим --fit auto это стережёт.

  python matte.py --video in.mp4 --bg bg.mp4 --out out.mp4
  python matte.py --video in.mp4 --bg green --from 3 --to 6 --out check.mp4 --check runs/.../fon   # проба края
"""
import argparse, subprocess, sys, time
from pathlib import Path
import numpy as np
import onnxruntime as ort
import cv2
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matte_core import (probe, reader, read_frame, build_plate, PlateTracker, refine_with_plate,
                        foreground_colors, ChatterReducer, Background, choke, repair_holes)

p = argparse.ArgumentParser()
p.add_argument("--video", required=True)
p.add_argument("--bg", required=True, help="картинка, видео или green — проверка края на зелёном")
p.add_argument("--out", required=True)
p.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "rvm_mobilenetv3_fp32.onnx"))
p.add_argument("--downsample", type=float, default=0.4)
p.add_argument("--fps", type=float, default=0.0, help="0 — как у исходника")
p.add_argument("--from", dest="t0", type=float, default=None, help="обработать кусок: начало, с")
p.add_argument("--to", dest="t1", type=float, default=None, help="обработать кусок: конец, с")
# вырезка
p.add_argument("--plate", choices=["auto", "off"], default="auto", help="ключ по чистой подложке стены")
p.add_argument("--plate-from", default="", help="видео, по которому строить подложку (по умолчанию --video)")
p.add_argument("--plate-cache", default="", help="npz: сохранить или взять готовую подложку")
p.add_argument("--plate-strength", type=float, default=1.0)
p.add_argument("--chatter", type=float, default=0.55, help="0..0.8: подавление дрожи маски во времени")
p.add_argument("--shrink", type=float, default=0.04, help="подрезка полупрозрачной кромки")
p.add_argument("--choke", type=int, default=1, help="подрезать маску внутрь на столько пикселей (светлая кромка)")
p.add_argument("--edge-soft", type=float, default=0.6, help="размытие кромки маски, px")
p.add_argument("--despill", type=float, default=0.0, help="0..1 снятие зелёного отлива — только для зелёного фона")
# внешний вид
p.add_argument("--grade", default="1.0,1.0,1.0", help="множители R,G,B под свет фона")
p.add_argument("--exposure", type=float, default=1.0)
p.add_argument("--head", default="", help="x,y,w,h лица в долях кадра (из quality.py): центр света")
p.add_argument("--relight", type=float, default=0.0, help="0..1: ниже лица человек темнее, как под лампой")
p.add_argument("--lightwrap", type=float, default=0.2, help="0..1: свет фона на кромке")
# фон
p.add_argument("--bg-blur", type=float, default=0.0, help="глубина резкости фона, sigma в px")
p.add_argument("--bg-slow", type=float, default=1.0, help="замедлить видео фона во столько раз")
p.add_argument("--bg-zoom", type=float, default=1.0)
p.add_argument("--bg-dx", type=int, default=0)
p.add_argument("--bg-push", type=float, default=0.04, help="наезд на картинку фона за ролик")
# кадрирование
p.add_argument("--scale", type=float, default=1.0)
p.add_argument("--dx", type=int, default=0)
p.add_argument("--dy", type=int, default=0)
p.add_argument("--fit", choices=["auto", "free"], default="auto", help="auto: не даёт показать срез на краях исходника")
p.add_argument("--feather", type=int, default=14, help="затухание альфы у срезанных краёв исходника, px")
# проверка
p.add_argument("--alpha-out", default="", help="записать маску отдельным видео (.mkv — без потерь)")
p.add_argument("--fg-out", default="",
               help="записать человека отдельным слоем (цвет, умноженный на маску); фон потом подставляет fon_compose.py")
p.add_argument("--check", default="", help="папка: кадры проверки края (голова крупно на зелёном и на фоне, низ кадра)")
p.add_argument("--quiet", action="store_true")
# старые флаги первой версии — больше не нужны
for old in ("--unmix", "--unmix-t", "--fill-holes"):
    p.add_argument(old, default=None, help="устарел: заменён ключом по подложке")
a = p.parse_args()


def log(*x):
    if not a.quiet:
        print(*x, flush=True)


for old in ("unmix", "unmix_t", "fill_holes"):
    if getattr(a, old) is not None:
        log(f"  ! --{old.replace('_', '-')} устарел и не действует: край и дыры теперь решает ключ по подложке стены")

W, H, src_fps, dur = probe(a.video)
FPS = a.fps or src_fps
t0 = a.t0 or 0.0
t1 = min(a.t1, dur) if a.t1 else dur
N = int(round((t1 - t0) * FPS))

sess = ort.InferenceSession(a.model, providers=["CPUExecutionProvider"])
DSR = np.array([a.downsample], np.float32)
DSR_HALF = np.array([min(1.0, a.downsample * 2)], np.float32)
ZERO = [np.zeros((1, 1, 1, 1), np.float32)] * 4


def rvm(frame, rec, dsr=DSR):
    fgr, pha, *rec = sess.run(["fgr", "pha", "r1o", "r2o", "r3o", "r4o"],
                              {"src": frame.transpose(2, 0, 1)[None], "r1i": rec[0], "r2i": rec[1],
                               "r3i": rec[2], "r4i": rec[3], "downsample_ratio": dsr})
    return pha[0, 0], rec


# ================= 1. РАЗВЕДКА: касается ли человек краёв кадра =================
def probe_edges(n=5):
    rec = ZERO
    rd = reader(a.video, W, H, ss=t0 if t0 else None)
    hits = {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0}
    got = idx = 0
    while got < n:
        fr = read_frame(rd, W, H)
        if fr is None:
            break
        idx += 1
        if idx % 12:
            continue
        al, rec = rvm(fr, rec)
        hits["left"] = max(hits["left"], (al[:, :2] > 0.5).mean())
        hits["right"] = max(hits["right"], (al[:, -2:] > 0.5).mean())
        hits["bottom"] = max(hits["bottom"], (al[-2:, :] > 0.5).mean())
        hits["top"] = max(hits["top"], (al[:2, :] > 0.5).mean())
        got += 1
    rd.kill()
    return {k: v > 0.01 for k, v in hits.items()}


scale, dx, dy = a.scale, a.dx, a.dy
edges = {"left": False, "right": False, "bottom": False, "top": False}
if a.fit == "auto":
    edges = probe_edges()
    log(f"разведка кадра: касание краёв {', '.join(k for k, v in edges.items() if v) or 'нет'}")
    nw = W * scale
    if edges["left"] and edges["right"] and scale < 1.0:
        log(f"  ! человек обрезан слева и справа — масштаб {scale} показал бы срез, поднимаю до 1.0")
        scale, nw = 1.0, W
    ox = (W - nw) / 2 + dx
    if edges["left"] and ox > 0:
        log(f"  ! левый срез уехал бы внутрь кадра — сдвигаю влево на {int(ox)}px")
        dx -= int(ox)
    ox = (W - nw) / 2 + dx
    if edges["right"] and ox + nw < W:
        log("  ! правый срез уехал бы внутрь кадра — сдвигаю вправо")
        dx += int(W - (ox + nw))
    nh = H * scale
    oy = (H - nh) + dy
    if edges["bottom"] and oy + nh < H:
        log("  ! нижний срез уехал бы внутрь кадра — прижимаю к низу")
        dy += int(H - (oy + nh))

# ================= 2. ПОДЛОЖКА СТЕНЫ =================
tracker = None
if a.plate == "auto":
    P = None
    cache = Path(a.plate_cache) if a.plate_cache else None
    if cache and cache.exists():
        z = np.load(cache)
        P = {"plate": z["plate"], "seen": z["seen"], "conf": z["conf"], "q": int(z["q"])}
        log(f"подложка стены: из {cache}")
    else:
        started = time.time()
        src = a.plate_from or a.video
        P = build_plate(src, W, H, lambda fr: rvm(fr, ZERO, DSR_HALF)[0], log=log)
        log(f"  построена за {time.time() - started:.0f} с")
        if P and cache:
            np.savez_compressed(cache, plate=P["plate"], seen=P["seen"], conf=P["conf"], q=P["q"])
    if P is not None:
        tracker = PlateTracker(P, W, H)
    else:
        log("  ! стена не найдена — работаю только по нейросети")

# ================= 3. ФОН, КРАЯ, СВЕТ =================
GREEN = a.bg.lower() == "green"
BGsrc = None if GREEN else Background(a.bg, W, H, N, fps=FPS, blur=a.bg_blur, slow=a.bg_slow,
                                      zoom=a.bg_zoom, dx=a.bg_dx, push=a.bg_push, log=log)
green = np.zeros((H, W, 3), np.float32)
green[..., 1] = 0.69
green[..., 2] = 0.25

edge_mask = np.ones((H, W), np.float32)
# Растушёвка нужна, только когда срез исходника может оказаться внутри кадра
# (человек уменьшен или сдвинут). При масштабе 1 край кадра и есть край среза —
# растушёвка лишь делала руку у края полупрозрачной.
if a.feather > 0 and (scale < 1.0 or dx or dy):
    f = a.feather
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    if edges.get("left"):
        edge_mask[:, :f] *= ramp[None, :]
    if edges.get("right"):
        edge_mask[:, -f:] *= ramp[::-1][None, :]
    if edges.get("top"):
        edge_mask[:f, :] *= ramp[:, None]

LIGHT = None
if a.relight > 0:
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    fy = float(a.head.split(",")[1]) if a.head else 0.35
    ramp = np.clip((yy - fy) / (1.0 - fy), 0, 1)
    LIGHT = (1.0 - a.relight * ramp ** 1.2)[..., None] * np.ones((1, W, 1), np.float32)

HEADBOX = None
if a.head:
    hx, hy, hw_, hh_ = (float(v) for v in a.head.split(","))
    HEADBOX = (int((hx - 0.9 * hw_) * W), int((hy - 1.0 * hh_) * H), int(1.8 * hw_ * W), int(1.6 * hh_ * H))

gr = np.array([float(x) for x in a.grade.split(",")], np.float32).reshape(1, 1, 3)
chatter = ChatterReducer(W, H, strength=a.chatter)

# ================= 4. ПРОХОД =================
rd = reader(a.video, W, H, ss=t0 if t0 else None, to=a.t1)
ss_a = f"-ss {t0} " if t0 else ""
to_a = f"-t {t1 - t0} " if a.t1 else ""
wr = subprocess.Popen(
    f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - '
    f'{ss_a}{to_a}-i "{a.video}" -map 0:v -map 1:a? -c:v libx264 -preset medium -crf 17 '
    f'-pix_fmt yuv420p -c:a aac -b:a 192k -shortest "{a.out}" -y',
    shell=True, stdin=subprocess.PIPE)
wa = None
if a.alpha_out:
    codec = "-c:v ffv1 -pix_fmt gray" if a.alpha_out.lower().endswith(".mkv") else         "-c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p"
    wa = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt gray -s {W}x{H} -r {FPS} -i - {codec} "{a.alpha_out}" -y',
        shell=True, stdin=subprocess.PIPE)
wf = None
if a.fg_out:
    wf = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {ss_a}{to_a}-i "{a.video}" '
        f'-map 0:v -map 1:a? -c:v libx264 -preset medium -crf 8 -pix_fmt yuv444p -c:a aac -b:a 256k '
        f'-shortest "{a.fg_out}" -y', shell=True, stdin=subprocess.PIPE)

check_at = set()
if a.check:
    Path(a.check).mkdir(parents=True, exist_ok=True)
    check_at = {int(N * k / 5) for k in range(1, 5)}

rec = ZERO
n = 0
started = time.time()
spent = {}
mark = [time.time()]


def tick(name):
    now = time.time()
    spent[name] = spent.get(name, 0.0) + now - mark[0]
    mark[0] = now


while True:
    mark[0] = time.time()
    I = read_frame(rd, W, H)
    if I is None or n >= N + 1:
        break
    tick("чтение")
    a_nn, rec = rvm(I, rec)
    tick("нейросеть")

    B = None
    alpha = a_nn
    if tracker is not None:
        B = tracker.frame(I, a_nn)
        alpha = refine_with_plate(I, a_nn, B, tracker.conf_full, strength=a.plate_strength)
        tick("ключ по стене")
    alpha = chatter(I, alpha)
    if tracker is not None:
        alpha, _ = repair_holes(I, alpha, B)      # страховка: дыра могла прийти из прошлого кадра
    tick("дрожь")
    if a.shrink > 0:
        alpha = np.clip((alpha - a.shrink) / (1.0 - a.shrink), 0, 1)
    alpha = choke(alpha, a.choke, a.edge_soft)
    alpha = alpha * edge_mask

    F = foreground_colors(I, alpha, plate=B)
    tick("цвет края")
    if a.despill > 0:
        rb = (F[..., 0] + F[..., 2]) * 0.5
        exc = np.maximum(F[..., 1] - rb, 0.0)
        F[..., 1] -= exc * a.despill
        F = np.clip(F + (exc * a.despill * 0.35)[..., None], 0, 1)

    if scale != 1.0 or dx or dy:
        nw, nh = int(W * scale), int(H * scale)
        fi = cv2.resize(F, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        ai = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        cf = np.zeros((H, W, 3), np.float32)
        ca = np.zeros((H, W), np.float32)
        ox, oy = (W - nw) // 2 + dx, (H - nh) + dy
        sx0, sy0, dx0, dy0 = max(0, -ox), max(0, -oy), max(0, ox), max(0, oy)
        cw, ch = min(nw - sx0, W - dx0), min(nh - sy0, H - dy0)
        if cw > 0 and ch > 0:
            cf[dy0:dy0 + ch, dx0:dx0 + cw] = fi[sy0:sy0 + ch, sx0:sx0 + cw]
            ca[dy0:dy0 + ch, dx0:dx0 + cw] = ai[sy0:sy0 + ch, sx0:sx0 + cw]
        F, alpha = cf, np.clip(ca, 0, 1)

    F = np.clip(F * gr * a.exposure, 0, 1)
    if LIGHT is not None:
        F = np.clip(F * LIGHT, 0, 1)

    if wf:
        wf.stdin.write(cv2.convertScaleAbs(F * alpha[..., None], alpha=255.0).tobytes())
    bg = green if GREEN else BGsrc.next()
    tick("фон")
    al = alpha[..., None]
    if a.lightwrap > 0 and not GREEN:
        # свет фона заходит на кромку изнутри: размытый фон поверх края человека
        small = cv2.resize(bg, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        bgb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (W, H), interpolation=cv2.INTER_LINEAR)
        inv = cv2.GaussianBlur(1.0 - alpha, (0, 0), 5)
        lw = np.clip(inv * alpha * 2.0, 0, 1)[..., None] * a.lightwrap
        F = F * (1 - lw) + bgb * lw

    comp = cv2.blendLinear(np.ascontiguousarray(F, np.float32), np.ascontiguousarray(bg, np.float32),
                           alpha, (1.0 - alpha).astype(np.float32))
    out8 = cv2.convertScaleAbs(comp, alpha=255.0)
    wr.stdin.write(out8.tobytes())
    if wa:
        wa.stdin.write((np.clip(alpha, 0, 1) * 255).astype(np.uint8).tobytes())

    if n in check_at:
        base = Path(a.check) / f"k{n:04d}"
        cv2.imwrite(str(base) + "-kadr.jpg", cv2.cvtColor(cv2.resize(out8, (W // 2, H // 2)), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        gcomp = (np.clip(F * al + green * (1 - al), 0, 1) * 255).astype(np.uint8)
        if HEADBOX:
            x, y, bw, bh = HEADBOX
            x, y = max(0, x), max(0, y)
            crop = np.concatenate([gcomp[y:y + bh, x:x + bw], out8[y:y + bh, x:x + bw]], axis=1)
            cv2.imwrite(str(base) + "-golova.png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        low = np.concatenate([gcomp[H - 560:, :], out8[H - 560:, :]], axis=0)
        cv2.imwrite(str(base) + "-niz.jpg", cv2.cvtColor(cv2.resize(low, (W // 2, 560)), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    tick("сведение и запись")
    n += 1
    if n % 60 == 0:
        el = time.time() - started
        log(f"  кадр {n}/{N}  {el / n:.2f} с/кадр, осталось ≈{(N - n) * el / n / 60:.1f} мин")

wr.stdin.close()
wr.wait()
if wa:
    wa.stdin.close()
    wa.wait()
if wf:
    wf.stdin.close()
    wf.wait()
rd.kill()
if BGsrc:
    BGsrc.close()
log(f"склеек в исходнике (маска не смешивалась через них): {chatter.cuts}")
if n:
    log("время на кадр: " + ", ".join(f"{k} {v / n:.2f} с" for k, v in spent.items()))
log(f"готово: {n} кадров за {(time.time() - started) / 60:.1f} мин → {a.out}")
