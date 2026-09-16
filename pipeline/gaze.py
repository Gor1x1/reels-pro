"""
Где говорящий смотрит вниз — в листок, в телефон, в суфлёр под камерой.

Зачем. Владелец читает текст с листа, и в первой сборке это было видно: взгляд
уходит вниз, зритель сразу понимает, что текст не свой. Такие куски либо
вырезаются, если в них нет нужной речи, либо закрываются вставкой.

    python gaze.py rech.mp4 --segments edl.json --sheet runs/x/gaze.png --json runs/x/gaze.json
    python gaze.py raw.mp4 --from 20 --to 75 --sheet gaze.png

Основной признак — модель лица MediaPipe с веками и зрачками: она прямо
оценивает, опущены ли глаза («eyeLookDown»). Калибровка на рилсе 1: говорит
в камеру — 0.08–0.20, смотрит в листок — 0.34–0.54. Порог 0.30, моргание
отсекается длительностью: короче 0.3 с — не взгляд.

Запасной признак без MediaPipe — пять точек YuNet (наклон головы и темнота
глаз). Он пропускает чтение, когда голова не наклоняется и опускаются только
глаза, — так на рилсе 1 и было. Использовать только если MediaPipe недоступен.

Пороги считаются от самого ролика: основное время человек смотрит в камеру,
медиана и есть «прямо». Всё найденное скрипт кладёт в лист крупных планов —
решение принимается глазами, числа только показывают, куда смотреть.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

try:
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

YUNET = Path(__file__).resolve().parent.parent / "models" / "face_detection_yunet_2023mar.onnx"
FPS = 10
W, H = 540, 960


def frames(src: str, a: float, b: float):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src,
         "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    arr = np.frombuffer(raw[: n * W * H * 3], np.uint8).reshape(n, H, W, 3)
    for i in range(n):
        yield a + i / FPS, arr[i]


MP_MODEL = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"


def mp_landmarker():
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision, BaseOptions
    except Exception:
        return None, None
    if not MP_MODEL.exists():
        return None, None
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(MP_MODEL)),
                                        output_face_blendshapes=True, num_faces=1)
    return mp, vision.FaceLandmarker.create_from_options(opts)


def mp_features(mp, lm, img_bgr):
    rgb = np.ascontiguousarray(img_bgr[..., ::-1])
    r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not r.face_blendshapes:
        return None
    b = {c.category_name: c.score for c in r.face_blendshapes[0]}
    pts = r.face_landmarks[0]
    xs = [q.x for q in pts]
    ys = [q.y for q in pts]
    box = [min(xs) * W, min(ys) * H, (max(xs) - min(xs)) * W, (max(ys) - min(ys)) * H]
    return {"down": (b["eyeLookDownLeft"] + b["eyeLookDownRight"]) / 2,
            "blink": (b["eyeBlinkLeft"] + b["eyeBlinkRight"]) / 2,
            "up": (b["eyeLookUpLeft"] + b["eyeLookUpRight"]) / 2,
            "box": box}


def features(det, img):
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return None
    f = max(faces, key=lambda r: r[2] * r[3])
    x, y, w, h = f[:4]
    re, le, nose, rm, lm = f[4:6], f[6:8], f[8:10], f[10:12], f[12:14]
    eye_y = (re[1] + le[1]) / 2
    mouth_y = (rm[1] + lm[1]) / 2
    pitch = (nose[1] - eye_y) / max(mouth_y - eye_y, 1)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    face = gray[max(int(y), 0): int(y + h), max(int(x), 0): int(x + w)]
    base = np.median(face) if face.size else 128
    r = max(int(w * 0.09), 4)
    dark = []
    for ex, ey in (re, le):
        box = gray[max(int(ey - r * 0.7), 0): int(ey + r * 0.7), max(int(ex - r), 0): int(ex + r)]
        if box.size:
            dark.append(float((box < base * 0.55).mean()))
    return {"pitch": float(pitch), "eyes": float(np.mean(dark)) if dark else None,
            "box": [float(x), float(y), float(w), float(h)]}


def spans(flags: list[tuple[float, bool]], min_len: float) -> list[list[float]]:
    out, start = [], None
    for t, f in flags:
        if f and start is None:
            start = t
        elif not f and start is not None:
            if t - start >= min_len:
                out.append([round(start, 2), round(t, 2)])
            start = None
    if start is not None and flags and flags[-1][0] + 1 / FPS - start >= min_len:
        out.append([round(start, 2), round(flags[-1][0] + 1 / FPS, 2)])
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="где говорящий смотрит вниз")
    p.add_argument("src")
    p.add_argument("--segments", help="edl.json от jumpcut: проверять только оставленные куски исходника")
    p.add_argument("--from", dest="t0", type=float)
    p.add_argument("--to", dest="t1", type=float)
    p.add_argument("--pitch-up", type=float, default=0.07, help="насколько выше медианы наклон считается взглядом вниз")
    p.add_argument("--eyes-drop", type=float, default=0.55, help="доля от медианной темноты глаз, ниже — веки прикрыты")
    p.add_argument("--min", type=float, default=0.3, help="короче — моргание, не взгляд")
    p.add_argument("--down", type=float, default=0.30, help="порог MediaPipe: глаза опущены")
    p.add_argument("--sheet")
    p.add_argument("--json")
    a = p.parse_args()

    if a.segments:
        segs = [s["src"] for s in json.loads(Path(a.segments).read_text(encoding="utf-8"))["segments"]]
    else:
        segs = [[a.t0 or 0.0, a.t1 or 1e9]]

    mp, lm = mp_landmarker()
    if lm is not None:
        print("движок: MediaPipe, веки и зрачки")
        rows = []
        for s, e in segs:
            for t, img in frames(a.src, s, e):
                rows.append((t, mp_features(mp, lm, img), img if a.sheet else None))
        flags, found = [], []
        for t, fe, img in rows:
            if fe is None:
                bad, why = True, ["лица нет"]
            else:
                bad = fe["down"] > a.down and fe["up"] < 0.1
                why = [f"вниз {fe['down']:.2f}"] if bad else []
            flags.append((t, bad))
            if bad:
                found.append((t, why, fe, img))
        result = []
        for s, e in segs:
            result += spans([(t, f) for t, f in flags if s <= t < e], a.min)
        print(f"кадров {len(rows)}; с опущенными глазами {len(found)}")
        for sp in result:
            print(f"  смотрит вниз: {sp[0]:.2f}-{sp[1]:.2f}")
        if a.json:
            Path(a.json).write_text(json.dumps({"engine": "mediapipe", "spans": result,
                                                "frames": [{"t": round(t, 2), "why": w} for t, w, _, _ in found]},
                                               ensure_ascii=False, indent=1), encoding="utf-8")
        if a.sheet:
            make_sheet(a.sheet, rows, found)
        return 0

    print("MediaPipe недоступен — запасной детектор по пяти точкам, чтение глазами без наклона головы он пропускает")
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (W, H), 0.7, 0.3, 10)
    rows = []
    for s, e in segs:
        for t, img in frames(a.src, s, e):
            fe = features(det, img)
            rows.append((t, fe, img if a.sheet else None))

    pitches = [r[1]["pitch"] for r in rows if r[1]]
    eyes = [r[1]["eyes"] for r in rows if r[1] and r[1]["eyes"] is not None]
    if not pitches:
        print("лицо не найдено")
        return 1
    mp, me = float(np.median(pitches)), float(np.median(eyes)) if eyes else 0.0

    flags, found = [], []
    for t, fe, img in rows:
        bad = False
        why = []
        if fe is None:
            bad, why = True, ["лица нет"]
        else:
            if fe["pitch"] > mp + a.pitch_up:
                bad = True
                why.append(f"наклон {fe['pitch']:.2f}")
            if me and fe["eyes"] is not None and fe["eyes"] < me * a.eyes_drop:
                bad = True
                why.append(f"глаза {fe['eyes']:.2f}")
        flags.append((t, bad))
        if bad:
            found.append((t, why, fe, img))

    # внутри одного куска исходника подряд, между кусками — разрыв
    result = []
    for s, e in segs:
        part = [(t, f) for t, f in flags if s <= t < e]
        result += spans(part, a.min)

    print(f"медиана: наклон {mp:.3f}, глаза {me:.3f}; кадров {len(rows)}; подозрительных кадров {len(found)}")
    for sp in result:
        print(f"  смотрит вниз: {sp[0]:.2f}-{sp[1]:.2f}")

    if a.json:
        Path(a.json).write_text(json.dumps({"median_pitch": mp, "median_eyes": me, "spans": result,
                                            "frames": [{"t": round(t, 2), "why": w} for t, w, _, _ in found]},
                                           ensure_ascii=False, indent=1), encoding="utf-8")

    if a.sheet:
        make_sheet(a.sheet, rows, found)
    return 0


def make_sheet(path, rows, found):
    if True:
        # крупные планы лица: подозрительные кадры и для сравнения — обычные
        picks = [(t, w, fe, img) for t, w, fe, img in found][:40]
        normal = [(t, ["норма"], fe, img) for t, fe, img in rows if fe and all(t != q[0] for q in found)][::25][:10]
        cells = []
        for t, why, fe, img in normal + picks:
            if fe:
                x, y, w, h = fe["box"]
                cx, cy, side = x + w / 2, y + h / 2, max(w, h) * 1.5
                x0, y0 = int(max(cx - side / 2, 0)), int(max(cy - side / 2, 0))
                crop = img[y0: int(y0 + side), x0: int(x0 + side)]
            else:
                crop = img[: W, :]
            c = cv2.resize(crop, (200, 200)) if crop.size else np.zeros((200, 200, 3), np.uint8)
            cv2.rectangle(c, (0, 0), (200, 22), (0, 0, 0), -1)
            color = (80, 220, 80) if why == ["норма"] else (60, 60, 255)
            cv2.putText(c, f"{t:.1f}s {' '.join(why)}"[:30], (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
            cells.append(c)
        cols = 8
        while len(cells) % cols:
            cells.append(np.zeros((200, 200, 3), np.uint8))
        sheet = np.vstack([np.hstack(cells[i: i + cols]) for i in range(0, len(cells), cols)])
        cv2.imwrite(path, sheet)
        print(f"лист: {path}")


if __name__ == "__main__":
    raise SystemExit(main())
