"""
Умное кадрирование горизонтали в вертикаль.

Обычный кроп режет по центру вслепую: если человек стоит сбоку, ему отрезает
половину, а если действие происходит в углу — оно просто не попадает в кадр.
Скрипт сначала смотрит, где в кадре главное, и ведёт окно за ним.

    python smartcrop.py in.mp4 --out public/src/clip.mp4
    python smartcrop.py in.mp4 --out out.mp4 --track motion --preview

Как ищет главное:
  1. лица (быстрый детектор OpenCV) — если человек в кадре, ведём за ним;
  2. движение — центр масс межкадровой разницы, если лиц нет;
  3. центр кадра — если не нашлось ни того, ни другого.

Траектория сглаживается и превращается в выражение для ffmpeg, поэтому окно
едет плавно, без рывков на каждом кадре.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
OUT_W, OUT_H = 1080, 1920
TARGET_AR = 9 / 16


def load_cv2():
    try:
        import cv2  # type: ignore
        return cv2
    except ImportError:
        print("нужен opencv: python -m pip install opencv-python")
        return None


def track(path: str, mode: str, samples: int = 60) -> list[tuple[float, float]]:
    """
    Возвращает список (время, x_центра в долях ширины).
    Пустой список — значит вести не за чем, кроп будет по центру.
    """
    cv2 = load_cv2()
    if cv2 is None:
        return []

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1
    if total <= 0:
        cap.release()
        return []

    step = max(total // samples, 1)
    cascade = None
    if mode in ("auto", "face"):
        xml = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if xml.exists():
            cascade = cv2.CascadeClassifier(str(xml))

    points: list[tuple[float, float]] = []
    faces_found = 0
    prev_gray = None
    idx = 0

    while True:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (0, 0), fx=0.4, fy=0.4)
        t = idx / fps
        cx = None

        if cascade is not None:
            faces = cascade.detectMultiScale(small, 1.2, 5, minSize=(30, 30))
            if len(faces):
                # берём самое крупное лицо — оно и есть герой кадра
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w / 2) / small.shape[1]
                faces_found += 1

        if cx is None and mode in ("auto", "motion") and prev_gray is not None:
            diff = cv2.absdiff(small, prev_gray)
            _, mask = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
            m = cv2.moments(mask)
            if m["m00"] > small.size * 0.5:  # движения достаточно, чтобы верить
                cx = (m["m10"] / m["m00"]) / small.shape[1]

        if cx is not None:
            points.append((t, min(max(cx, 0.0), 1.0)))

        prev_gray = small
        idx += step
        if idx >= total:
            break

    cap.release()

    if mode == "auto" and faces_found < len(points) * 0.3 and not points:
        return []
    return points


def smooth(points: list[tuple[float, float]], window: int = 5) -> list[tuple[float, float]]:
    """Скользящее среднее: без него окно дёргается на каждом ложном срабатывании."""
    if len(points) < 3:
        return points
    out = []
    for i, (t, _) in enumerate(points):
        lo, hi = max(0, i - window // 2), min(len(points), i + window // 2 + 1)
        avg = sum(p[1] for p in points[lo:hi]) / (hi - lo)
        out.append((t, avg))
    return out


def crop_expr(points: list[tuple[float, float]], src_w: int, crop_w: int) -> str:
    """
    Строит выражение x(t) для фильтра crop: кусочно-линейная траектория окна.
    Больше 12 узлов не берём — выражение становится длиннее, чем терпит ffmpeg.
    """
    max_x = src_w - crop_w
    if not points:
        return f"{max_x // 2}"

    if len(points) > 12:
        k = len(points) / 12
        points = [points[int(i * k)] for i in range(12)]

    def px(cx: float) -> int:
        return int(min(max(cx * src_w - crop_w / 2, 0), max_x))

    # собираем вложенные if по времени: if(lt(t,t1), x0+(x1-x0)*..., ...)
    expr = str(px(points[-1][1]))
    for i in range(len(points) - 2, -1, -1):
        t0, c0 = points[i]
        t1, c1 = points[i + 1]
        x0, x1 = px(c0), px(c1)
        dt = max(t1 - t0, 0.001)
        seg = f"{x0}+({x1 - x0})*(t-{t0:.2f})/{dt:.2f}"
        expr = f"if(lt(t,{t1:.2f}),{seg},{expr})"
    return expr


def probe_size(path: str) -> tuple[int, int]:
    out = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        w, h = (int(x) for x in out.split(",")[:2])
        return w, h
    except ValueError:
        return 0, 0


def main() -> int:
    ap = argparse.ArgumentParser(description="умное кадрирование в вертикаль")
    ap.add_argument("src")
    ap.add_argument("--out", required=True)
    ap.add_argument("--track", choices=["auto", "face", "motion", "center"], default="auto")
    ap.add_argument("--preview", action="store_true", help="показать траекторию и выйти")
    args = ap.parse_args()

    w, h = probe_size(args.src)
    if not w:
        print("не читается видео")
        return 1

    if h > w:
        print("исходник уже вертикальный — умное кадрирование не нужно, гони через prep.py")
        return 1

    crop_w = int(h * TARGET_AR) // 2 * 2
    pts = [] if args.track == "center" else smooth(track(args.src, args.track))

    if pts:
        spread = max(p[1] for p in pts) - min(p[1] for p in pts)
        print(f"найдено {len(pts)} точек, разброс по горизонтали {spread * 100:.0f}%")
        if spread < 0.04:
            # герой почти не двигается — статичное окно спокойнее, чем дрожащее
            avg = sum(p[1] for p in pts) / len(pts)
            pts = [(0.0, avg)]
            print("  движение маленькое, ставлю неподвижное окно")
    else:
        print("вести не за чем, кадрирую по центру")

    if args.preview:
        for t, cx in pts[:20]:
            print(f"  {t:6.2f} c   центр {cx * 100:5.1f}%")
        return 0

    x = crop_expr(pts, w, crop_w)
    vf = f"crop={crop_w}:{h}:'{x}':0,scale={OUT_W}:{OUT_H},fps=30"

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", args.src,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-af", "aresample=48000", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", args.out,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1500:])
        return 1

    print(f"готово: {args.out}  ({w}x{h} -> {OUT_W}x{OUT_H})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
