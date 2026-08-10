#!/usr/bin/env python3
"""
Замена фона в видео через AI-матирование (RobustVideoMatting).
Работает там, где обычный хромакей рвёт лицо: неровный свет, дешёвый зелёный фон.

Ключевое отличие от наивной реализации — БЕЗОПАСНОЕ КАДРИРОВАНИЕ.
Если человек в исходнике обрезан краем кадра (руки/плечи уходят за границу),
уменьшать его НЕЛЬЗЯ: срез уезжает внутрь кадра и получается «обрубок».
Режим --fit auto измеряет касание альфы к краям и сам не даёт этого сделать.

  python matte.py --video in.mp4 --bg bg.png --out out.mp4
"""
import argparse, subprocess, sys
import numpy as np
import onnxruntime as ort
from PIL import Image

p = argparse.ArgumentParser()
p.add_argument("--video", required=True)
p.add_argument("--bg", required=True, help="картинка или видео фона")
p.add_argument("--out", required=True)
p.add_argument("--model", default="/Users/georgidarbinyan/Developer/rvm/rvm_mobilenetv3_fp32.onnx")
p.add_argument("--downsample", type=float, default=0.4)
p.add_argument("--fps", type=float, default=30.0)
# внешний вид
p.add_argument("--grade", default="1.0,1.0,1.0", help="множители R,G,B под свет фона")
p.add_argument("--exposure", type=float, default=1.0)
p.add_argument("--despill", type=float, default=0.9, help="снятие зелёного отлива 0..1")
p.add_argument("--shrink", type=float, default=0.12, help="подрезка полупрозрачной кромки")
p.add_argument("--lightwrap", type=float, default=0.35, help="свет фона на кромке 0..1")
# кадрирование
p.add_argument("--scale", type=float, default=1.0)
p.add_argument("--dx", type=int, default=0)
p.add_argument("--dy", type=int, default=0)
p.add_argument("--fit", choices=["auto", "free"], default="auto",
               help="auto: не даёт показать срез на краях исходника")
p.add_argument("--feather", type=int, default=14,
               help="мягкое затухание альфы у краёв исходника, px")
p.add_argument("--bg-zoom", type=float, default=1.0, help="зум фона (композиция без уменьшения человека)")
p.add_argument("--bg-dx", type=int, default=0, help="сдвиг фона по X")
p.add_argument("--quiet", action="store_true")
a = p.parse_args()

def log(*x):
    if not a.quiet:
        print(*x, flush=True)

# --- размеры исходника ---
probe = subprocess.check_output(
    f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "{a.video}"',
    shell=True).decode().strip().split(",")
W, H = int(probe[0]), int(probe[1])

sess = ort.InferenceSession(a.model, providers=["CPUExecutionProvider"])
DSR = np.array([a.downsample], np.float32)

def alpha_of(frame_rgb, rec):
    src = frame_rgb.transpose(2, 0, 1)[None]
    fgr, pha, *rec = sess.run(
        ["fgr", "pha", "r1o", "r2o", "r3o", "r4o"],
        {"src": src, "r1i": rec[0], "r2i": rec[1], "r3i": rec[2], "r4i": rec[3],
         "downsample_ratio": DSR})
    return fgr[0].transpose(1, 2, 0), pha[0, 0], rec

# ================= 1. РАЗВЕДКА: касается ли человек краёв кадра =================
def probe_edges(n=5):
    rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4
    rd = subprocess.Popen(f'ffmpeg -v error -i "{a.video}" -f rawvideo -pix_fmt rgb24 -',
                          shell=True, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
    hits = {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0}
    got = 0
    idx = 0
    while got < n:
        raw = rd.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        idx += 1
        if idx % 12:                      # разрежённая выборка
            continue
        fr = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
        _, al, rec = alpha_of(fr, rec)
        hits["left"] = max(hits["left"], (al[:, :2] > 0.5).mean())
        hits["right"] = max(hits["right"], (al[:, -2:] > 0.5).mean())
        hits["bottom"] = max(hits["bottom"], (al[-2:, :] > 0.5).mean())
        hits["top"] = max(hits["top"], (al[:2, :] > 0.5).mean())
        got += 1
    rd.kill()
    return {k: v > 0.01 for k, v in hits.items()}, hits

scale, dx, dy = a.scale, a.dx, a.dy
edges = {"left": False, "right": False, "bottom": False, "top": False}

if a.fit == "auto":
    edges, raw_hits = probe_edges()
    log(f"разведка кадра: касание краёв {', '.join(k for k,v in edges.items() if v) or 'нет'}")
    nw = W * scale
    # оба борта срезаны → уменьшать нельзя вообще
    if edges["left"] and edges["right"] and scale < 1.0:
        log(f"  ! человек обрезан слева и справа — масштаб {scale} показал бы срез, поднимаю до 1.0")
        scale = 1.0
        nw = W
    ox = (W - nw) / 2 + dx
    if edges["left"] and ox > 0:
        log(f"  ! левый срез уехал бы внутрь кадра — сдвигаю влево на {int(ox)}px")
        dx -= int(ox)
    ox = (W - nw) / 2 + dx
    if edges["right"] and ox + nw < W:
        log(f"  ! правый срез уехал бы внутрь кадра — сдвигаю вправо")
        dx += int(W - (ox + nw))
    nh = H * scale
    oy = (H - nh) + dy
    if edges["bottom"] and oy + nh < H:
        log("  ! нижний срез уехал бы внутрь кадра — прижимаю к низу")
        dy += int(H - (oy + nh))

# ================= 2. ФОН =================
bg_is_video = a.bg.lower().endswith((".mp4", ".mov", ".m4v", ".webm"))
if not bg_is_video:
    bgim = Image.open(a.bg).convert("RGB")
    sc = max(W / bgim.width, H / bgim.height) * a.bg_zoom
    bgim = bgim.resize((int(bgim.width * sc + .5), int(bgim.height * sc + .5)), Image.LANCZOS)
    l = (bgim.width - W) // 2 + a.bg_dx
    t = (bgim.height - H) // 2
    l = max(0, min(bgim.width - W, l))
    t = max(0, min(bgim.height - H, t))
    BG = np.asarray(bgim.crop((l, t, l + W, t + H))).astype(np.float32) / 255.0
else:
    BG = None
    bgrd = subprocess.Popen(
        f'ffmpeg -v error -stream_loop -1 -i "{a.bg}" -vf scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H} '
        f'-f rawvideo -pix_fmt rgb24 -', shell=True, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)

# ================= 3. МАСКА СМЯГЧЕНИЯ КРАЁВ ИСХОДНИКА =================
edge_mask = np.ones((H, W), np.float32)
if a.feather > 0:
    f = a.feather
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    if edges.get("left"):
        edge_mask[:, :f] *= ramp[None, :]
    if edges.get("right"):
        edge_mask[:, -f:] *= ramp[::-1][None, :]
    if edges.get("top"):
        edge_mask[:f, :] *= ramp[:, None]
    # низ не смягчаем: человек «стоит» в кадре

# ================= 4. ПРОХОД =================
gr = np.array([float(x) for x in a.grade.split(",")], np.float32).reshape(1, 1, 3)
rec = [np.zeros((1, 1, 1, 1), np.float32)] * 4

rd = subprocess.Popen(f'ffmpeg -v error -i "{a.video}" -f rawvideo -pix_fmt rgb24 -',
                      shell=True, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)
wr = subprocess.Popen(
    f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {a.fps} -i - '
    f'-i "{a.video}" -map 0:v -map 1:a? -c:v libx264 -preset medium -crf 17 '
    f'-pix_fmt yuv420p -c:a aac -b:a 192k -shortest "{a.out}" -y',
    shell=True, stdin=subprocess.PIPE)

n = 0
while True:
    raw = rd.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        break
    frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
    fg, alpha, rec = alpha_of(frame, rec)

    if BG is None:
        braw = bgrd.stdout.read(W * H * 3)
        bg = np.frombuffer(braw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
    else:
        bg = BG

    # despill: снять зелёный отлив
    if a.despill > 0:
        rb = (fg[..., 0] + fg[..., 2]) * 0.5
        exc = np.maximum(fg[..., 1] - rb, 0.0)
        fg[..., 1] -= exc * a.despill
        fg += (exc * a.despill * 0.35)[..., None]
        fg = np.clip(fg, 0, 1)

    # подрезка полупрозрачной кромки
    if a.shrink > 0:
        alpha = np.clip((alpha - a.shrink) / (1.0 - a.shrink), 0, 1)

    # мягкое затухание у срезанных краёв исходника
    alpha = alpha * edge_mask

    # масштаб и положение
    if scale != 1.0 or dx or dy:
        nw, nh = int(W * scale), int(H * scale)
        fi = Image.fromarray((np.clip(fg, 0, 1) * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
        ai = Image.fromarray((np.clip(alpha, 0, 1) * 255).astype(np.uint8)).resize((nw, nh), Image.LANCZOS)
        cf = np.zeros((H, W, 3), np.float32)
        ca = np.zeros((H, W), np.float32)
        ox = (W - nw) // 2 + dx
        oy = (H - nh) + dy
        sx0, sy0 = max(0, -ox), max(0, -oy)
        dx0, dy0 = max(0, ox), max(0, oy)
        cw = min(nw - sx0, W - dx0)
        ch = min(nh - sy0, H - dy0)
        if cw > 0 and ch > 0:
            cf[dy0:dy0 + ch, dx0:dx0 + cw] = np.asarray(fi)[sy0:sy0 + ch, sx0:sx0 + cw] / 255.0
            ca[dy0:dy0 + ch, dx0:dx0 + cw] = np.asarray(ai)[sy0:sy0 + ch, sx0:sx0 + cw] / 255.0
        fg, alpha = cf, ca

    al = alpha[..., None]
    fg = np.clip(fg * gr * a.exposure, 0, 1)

    # light wrap: свет фона ложится на кромку
    if a.lightwrap > 0:
        edge = np.clip(al * (1 - al) * 4.0, 0, 1)
        fg = np.clip(fg * (1 - edge * a.lightwrap) + bg * (edge * a.lightwrap), 0, 1)

    comp = fg * al + bg * (1 - al)
    wr.stdin.write((np.clip(comp, 0, 1) * 255).astype(np.uint8).tobytes())
    n += 1
    if n % 60 == 0:
        log(f"  кадр {n}")

wr.stdin.close(); wr.wait(); rd.wait()
if BG is None:
    bgrd.kill()
log(f"готово: {n} кадров → {a.out}")
