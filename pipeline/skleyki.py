"""
Стыки глазами режиссёра: какая склейка клеится, а какую зритель заметит.

Зачем. Владелец 16.09.2026 объяснил монтаж как мышление (плейбук `монтаж`,
раздел «Монтажное мышление»):
- большую часть склеек держит эмоция;
- остальное держат точка внимания (после стыка глаза зрителя не ищут героя)
  и крупность (меняется на одну ступень).
Скрипт делает точку и крупность числами, а эмоцию — проверкой по карте
акцентов: нарушение без эмоции — брак, с эмоцией — приём.

    # где глаза на каждом куске речи: для faces и lock в сцене talk
    python pipeline/skleyki.py measure public/src/r1-fon.mp4 --edl runs/.../edl.json --json runs/.../glaza.json

    # план крупностей: ступень на каждой склейке, скачок — только на акценте
    python pipeline/skleyki.py plan --glaza runs/.../glaza.json --spec src/spec.json --scene 0 \
        --akcenty runs/.../akcenty.json [--write]

    # проверка готового ролика: каждый стык — крупность, сдвиг глаз, клей
    python pipeline/skleyki.py audit out/R1.mp4 --edl runs/.../edl.json --spec src/spec.json --scene 0 \
        --akcenty runs/.../akcenty.json --json runs/.../skleyki.json --sheet runs/.../skleyki.jpg

akcenty.json — эмоциональные акценты в секундах сцены (у сцены talk, которая
стоит первой, это секунды ролика):
    {"akcenty": [{"t": 2.4, "sila": 0.9, "chto": "цифра 5000 — удивление"}]}
Пишет их `montaj-smysl` по смыслу речи; `--from-src` переводит секунды
исходника через edl.json.

Пороги — из исследования 17.09.2026 (плейбук, М-32…М-38). Глаза меряются по
модели лица MediaPipe: середина между глазами и расстояние между ними. Их
отношение до и после стыка и есть смена крупности: мерить по наезду из спеки
нельзя — человек сам качается к камере и от неё.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MP_MODEL = ROOT / "models" / "face_landmarker.task"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Экран, на котором смотрят. Строгий профиль из исследования 17.09.2026:
# вертикальный ролик во всю ширину большого телефона (7.5 см), до глаз 25 см.
# Если порог держится здесь, он держится на любом телефоне.
SCREEN_W_CM = 7.5
SCREEN_H_CM = SCREEN_W_CM * 16 / 9
VIEW_CM = 25.0

# Пороги по умолчанию — плейбук, точка внимания М-33, крупность М-34.
# До 0.5° глаз не делает саккады, до 1° — поправка без поиска (фовеа),
# от 2° — полная переориентация: 0.2–0.85 с зритель ищет героя.
EYE_EXACT_DEG = 0.5
EYE_OK_DEG = 1.0
EYE_BAD_DEG = 2.0
# Крупность — отношение расстояний между глазами у соседних кусков (М-35):
# меньше 1.10 — та же крупность; 1.10–1.40 — серая зона, «чуть теснее»: смену
# видно, а нового кадра нет — хуже всего (Мёрч); 1.40–1.85 — ступень;
# 1.85–2.9 — через ступень, только на акценте; больше 2.9 — только пик эмоции.
SIZE_SAME = 1.10
SIZE_STEP = 1.40
SIZE_TWO = 1.85
SIZE_PEAK = 2.9
SERIES_MAX = 3       # стыков одной крупности подряд, дальше — смена (М-40)
ACCENT_WIN = 0.35    # акцент ближе к стыку, с — склейка эмоциональная
# Лестница из исходника по пояс: пояс → грудь → плечи и лицо (М-35).
LADDER = [1.0, 1.6, 2.4]


# ---------- кадры и глаза ----------

def probe(src: str) -> dict:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate:format=duration", "-of", "json", src],
                         capture_output=True, text=True, encoding="utf-8").stdout
    j = json.loads(out)
    s = j["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"w": int(s["width"]), "h": int(s["height"]), "fps": float(num) / float(den or 1),
            "dur": float(j["format"]["duration"])}


def small_size(info: dict, width: int = 540) -> tuple[int, int]:
    h = int(round(width * info["h"] / info["w"] / 2) * 2)
    return width, h


def frame_at(src: str, t: float, size: tuple[int, int]) -> np.ndarray | None:
    w, h = size
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(t, 0):.3f}", "-i", src, "-frames:v", "1",
                          "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    if len(raw) < w * h * 3:
        return None
    return np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3).copy()


def frames(src: str, a: float, b: float, fps: float, size: tuple[int, int]):
    w, h = size
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src,
                          "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    arr = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    for i in range(n):
        yield a + i / fps, arr[i]


def landmarker():
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    if not MP_MODEL.exists():
        sys.exit(f"нет модели лица: {MP_MODEL}")
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(MP_MODEL)), num_faces=1)
    return mp, vision.FaceLandmarker.create_from_options(opts)


def eyes_in(mp, lm, bgr: np.ndarray) -> dict | None:
    """
    Якорь внимания на лице (доли кадра) и расстояние между глазами (доля ширины).

    Якорь — середина между глазами и ртом, то есть около носа: у говорящего
    взгляд зрителя ходит между глазами и ртом и держится за нос, когда лицо
    движется (Võ et al. 2012). Расстояние между глазами — мера крупности:
    от позы и открытого рта оно не зависит.
    """
    h, w = bgr.shape[:2]
    r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(bgr[..., ::-1])))
    if not r.face_landmarks:
        return None
    p = r.face_landmarks[0]
    right = ((p[33].x + p[133].x) / 2, (p[33].y + p[133].y) / 2)
    left = ((p[362].x + p[263].x) / 2, (p[362].y + p[263].y) / 2)
    eyes = ((right[0] + left[0]) / 2, (right[1] + left[1]) / 2)
    mouth = ((p[13].x + p[14].x) / 2, (p[13].y + p[14].y) / 2)
    xs, ys = [q.x for q in p], [q.y for q in p]
    return {
        "x": round((eyes[0] + mouth[0]) / 2, 4),
        "y": round((eyes[1] + mouth[1]) / 2, 4),
        "mouth_y": round(mouth[1], 4),
        "iod": round(math.hypot((left[0] - right[0]) * w, (left[1] - right[1]) * h) / w, 4),
        "w": round(max(xs) - min(xs), 4),
        "h": round(max(ys) - min(ys), 4),
    }


def degrees(dx: float, dy: float) -> float:
    """Сдвиг в долях кадра → угол зрения на телефоне, градусы."""
    cm = math.hypot(dx * SCREEN_W_CM, dy * SCREEN_H_CM)
    return math.degrees(2 * math.atan(cm / 2 / VIEW_CM))


# ---------- спека и акценты ----------

def load_segments(edl: str) -> list[dict]:
    return json.loads(Path(edl).read_text(encoding="utf-8"))["segments"]


def scene_offset(spec: dict, index: int) -> float:
    t = 0.0
    for sc in spec["scenes"][:index]:
        t += float(sc.get("dur") or sc.get("sec") or 0)
    return t


def src_to_out(t: float, segs: list[dict]) -> float | None:
    speed = 1.0
    for s in segs:
        a, b = s["src"]
        o0, o1 = s["out"]
        if a <= t <= b:
            speed = (b - a) / max(o1 - o0, 1e-6)
            return o0 + (t - a) / speed
    return None


def load_accents(path: str | None, segs: list[dict] | None, from_src: bool) -> list[dict]:
    if not path:
        return []
    items = json.loads(Path(path).read_text(encoding="utf-8")).get("akcenty", [])
    out = []
    for a in items:
        t = float(a["t"])
        if from_src and segs:
            t2 = src_to_out(t, segs)
            if t2 is None:
                continue
            t = t2
        out.append({**a, "t": t})
    return out


def windows(scene: dict) -> list[tuple[float, float]]:
    """Отрезки, где говорящий в окне: стык внутри окна мелкий, судить его как полный кадр нельзя."""
    return [(w0, w1) for w0, w1, _ in window_boxes(scene)]


def window_boxes(scene: dict) -> list[tuple[float, float, tuple[float, float]]]:
    """То же, с центром окна: туда уезжает лицо, туда же уходит взгляд зрителя."""
    res = []
    for l in scene.get("layers", []):
        pip = l.get("pip") or {}
        shape = pip.get("shape", "circle")
        if l.get("kind") == "insert" and shape != "none":
            center = (float(pip.get("x", 0.5)), float(pip.get("y", 0.68 if shape == "circle" else 0.27)))
            res.append((float(l["at"]), float(l["at"]) + float(l["dur"]), center))
    return res


def near(t: float, spans: list[tuple[float, float]], pad: float = 0.0) -> bool:
    return any(a - pad <= t <= b + pad for a, b in spans)


# ---------- measure ----------

def cmd_measure(a) -> int:
    info = probe(a.video)
    size = small_size(info)
    segs = load_segments(a.edl) if a.edl else [{"out": [0.0, info["dur"]]}]
    mp, lm = landmarker()
    rows = []
    for i, s in enumerate(segs):
        o0, o1 = s["out"]
        lo, hi = o0 + 0.06, max(o1 - 0.06, o0 + 0.07)
        got = [e for _, img in frames(a.video, lo, hi, a.fps, size) if (e := eyes_in(mp, lm, img))]
        if not got:
            mid = frame_at(a.video, (o0 + o1) / 2, size)
            e = eyes_in(mp, lm, mid) if mid is not None else None
            got = [e] if e else []
        if not got:
            rows.append({"i": i, "out": [o0, o1], "eyes": None})
            print(f"  кусок {i:2d} {o0:6.2f}-{o1:6.2f}: лица нет")
            continue
        med = {k: round(float(np.median([g[k] for g in got])), 4) for k in got[0]}
        spread = round(float(np.hypot(np.std([g["x"] for g in got]), np.std([g["y"] for g in got]))), 4)
        rows.append({"i": i, "out": [o0, o1], "eyes": med, "n": len(got), "spread": spread})
        print(f"  кусок {i:2d} {o0:6.2f}-{o1:6.2f}: глаза {med['x']:.3f},{med['y']:.3f}  "
              f"между глазами {med['iod']:.3f}  разброс {spread:.3f}")
    ok = [r["eyes"] for r in rows if r["eyes"]]
    median = {k: round(float(np.median([e[k] for e in ok])), 4) for k in ok[0]} if ok else None
    res = {"video": a.video, "edl": a.edl, "size": [info["w"], info["h"]], "segments": rows, "median": median}
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"записано: {a.json}")
    return 0


# ---------- plan ----------

def cmd_plan(a) -> int:
    g = json.loads(Path(a.glaza).read_text(encoding="utf-8"))
    spec_path = Path(a.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    scene = spec["scenes"][a.scene]
    segs = g["segments"]
    edl = load_segments(g["edl"]) if g.get("edl") and Path(g["edl"]).exists() else None
    accents = load_accents(a.akcenty, edl, a.from_src)
    wins = windows(scene)
    ladder = [float(x) for x in a.ladder.split(",")]

    # запас резкости: наезд из кадра размером с вывод — это растяжение пикселей
    out_h = 1920
    src_h = g.get("size", [0, out_h])[1]
    clean = src_h / out_h if src_h else 1.0
    if ladder[-1] > clean * 1.25:
        print(f"ВНИМАНИЕ: исходник {g.get('size')} даёт чистый наезд до {clean:.2f}, верхняя ступень "
              f"{ladder[-1]} растянет картинку в {ladder[-1] / clean:.2f} раза. Собирать кусок речи "
              f"в 1440×2560 или 2160×3840 (М-36).")

    marks: list[list[float]] = []
    faces: list[list] = []
    top = len(ladder) - 1
    # Бюджет акцентов: прыжков через ступень не больше трети стыков в полном кадре (М-37).
    full = [x for x in segs[1:] if not near(x["out"][0] + 0.02, wins)]
    budget = max(1, len(full) // 3)

    def accent_for(seg):
        o0, o1 = seg["out"]
        reach = min(o1, o0 + a.accent_reach)
        acc = [x for x in accents if o0 - ACCENT_WIN <= x["t"] <= reach and float(x.get("sila", 1)) >= a.min_sila]
        return max(acc, key=lambda x: float(x.get("sila", 1))) if acc else None

    strongest = sorted((x for x in full if accent_for(x)), key=lambda x: -float(accent_for(x).get("sila", 1)))
    allowed = {id(x) for x in strongest[:budget]}

    level = 0
    log = []
    for seg in segs:
        o0, o1 = seg["out"]
        if seg["eyes"]:
            faces.append([round(o0, 3), {k: seg["eyes"][k] for k in ("x", "y", "w", "h")}])
        if near(o0 + 0.02, wins):
            log.append(f"{o0:6.2f}        в окне — крупность не меняю")
            continue
        acc = accent_for(seg)
        if seg["i"] == 0:
            new, why = (top, f"хук на акценте «{acc.get('chto', '')}»") if acc else (0, "начало — база")
        elif acc and id(seg) in allowed:
            new, why = top, f"акцент «{acc.get('chto', '')}» — крупный на начало фразы"
        elif level == top:
            new, why = top - 1, "после акцента — ступень назад"
        else:
            new, why = (1 if level == 0 else 0), "ступень: «одинаковое на одинаковое» не клеится"
            if acc:
                why += " (акцент есть, но бюджет трети исчерпан)"
        level = new
        marks.append([round(o0, 3), ladder[level], 0])
        log.append(f"{o0:6.2f}  ×{ladder[level]:.2f}  {why}")

    print("\n".join(log))
    plan = {"zooms": marks, "faces": faces, "lock": True}
    if a.write:
        backup = spec_path.with_suffix(".before-skleyki.json")
        backup.write_text(spec_path.read_text(encoding="utf-8"), encoding="utf-8")
        scene.update(plan)
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"записано в {spec_path}, сцена {a.scene}; копия до правки — {backup.name}")
    else:
        print(json.dumps(plan, ensure_ascii=False))
    return 0


# ---------- audit ----------

def classify(before: dict | None, after: dict | None, accent: dict | None, in_window: bool,
             window_edge, a) -> dict:
    row: dict = {"akcent": accent.get("chto") if accent else None}
    if in_window or window_edge:
        row.update(klej="окно", verdict="переход окна" if window_edge else "в окне — стык мелкий", ok=True)
        if window_edge and isinstance(window_edge, tuple):
            # лицо уезжает в окно движением — глаз ведётся, но чем дальше окно, тем дольше поиск
            kind, center = window_edge
            face = before if kind == "in" else after
            if face:
                deg = degrees(center[0] - face["x"], center[1] - face["y"])
                row.update(deg=round(deg, 2), verdict=f"{'в окно' if kind == 'in' else 'из окна'}: "
                                                      f"взгляд за лицом на {deg:.1f}°")
        return row
    if not before or not after:
        row.update(klej="?", verdict="лица нет на одном из кадров — смотреть глазами", ok=None)
        return row
    ratio = after["iod"] / max(before["iod"], 1e-6)
    step = max(ratio, 1 / ratio)
    deg = degrees(after["x"] - before["x"], after["y"] - before["y"])
    size = ("та же" if step < a.size_same else "серая зона" if step < SIZE_STEP else "ступень" if step < a.size_two
            else "через ступень" if step < SIZE_PEAK else "пик")
    point = ("точно" if deg <= a.eye_exact else "на месте" if deg <= a.eye_ok
             else "сдвиг" if deg <= a.eye_bad else "прыжок")
    row.update(ratio=round(ratio, 3), deg=round(deg, 2), krupnost=size, tochka=point)
    problems = []
    if size == "серая зона":
        problems.append(f"крупность «чуть теснее» ×{step:.2f}")
    if size in ("через ступень", "пик"):
        problems.append(f"прыжок {size} ×{step:.2f}")
    if point == "прыжок":
        problems.append(f"глаза прыгнули на {deg:.1f}°")
    elif point == "сдвиг":
        problems.append(f"глаза сдвинулись на {deg:.1f}°")
    if accent:
        row.update(klej="эмоция", ok=True,
                   verdict="эмоция держит" + (f" (нарушено: {', '.join(problems)})" if problems else ""))
    elif size == "та же" and not problems:
        # стык вырезки: клей — непрерывный голос и точка на месте (М-40, ждёт решения владельца)
        exact = point == "точно"
        row.update(klej="звук" if exact else "нет", ok=None if exact else False,
                   verdict="та же крупность: держит только голос (М-40)" if exact
                   else f"та же крупность и глаза сдвинулись на {deg:.1f}°")
    elif size == "та же":
        row.update(klej="нет", ok=False, verdict="не клеится: та же крупность, " + ", ".join(problems))
    elif not problems:
        row.update(klej="точка и крупность", ok=True, verdict="клеится")
    else:
        row.update(klej="нет", ok=False, verdict="не клеится: " + ", ".join(problems))
    return row


def cmd_audit(a) -> int:
    info = probe(a.video)
    size = small_size(info)
    fps = info["fps"]
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8")) if a.spec else None
    scene = spec["scenes"][a.scene] if spec else {}
    offset = a.offset if a.offset is not None else (scene_offset(spec, a.scene) if spec else 0.0)
    segs = load_segments(a.edl)
    accents = load_accents(a.akcenty, segs, a.from_src)
    boxes = window_boxes(scene)
    mp, lm = landmarker()

    rows, pairs = [], []
    for i in range(1, len(segs)):
        c = float(segs[i]["out"][0])  # секунда сцены
        t = offset + c
        img0 = frame_at(a.video, t - 1.5 / fps, size)
        img1 = frame_at(a.video, t + 1.5 / fps, size)
        e0 = eyes_in(mp, lm, img0) if img0 is not None else None
        e1 = eyes_in(mp, lm, img1) if img1 is not None else None
        # акцент относится к стыку, если его слово во фразе, которая начинается стыком:
        # смена крупности ставится на начало фразы, а не на само слово (М-38)
        c_next = float(segs[i + 1]["out"][0]) if i + 1 < len(segs) else c + a.accent_reach
        reach = min(c_next, c + a.accent_reach)
        acc = [x for x in accents if c - ACCENT_WIN <= x["t"] <= reach and float(x.get("sila", 1)) >= a.min_sila]
        accent = max(acc, key=lambda x: float(x.get("sila", 1))) if acc else None
        in_win = near(c, [(w0, w1) for w0, w1, _ in boxes])
        edge = None
        for w0, w1, center in boxes:
            if abs(c - w0) < 0.12 and not any(abs(o1 - w0) < 0.12 for _, o1, _ in boxes):
                edge = ("in", center)
            elif abs(c - w1) < 0.12 and not any(abs(o0 - w1) < 0.12 for o0, _, _ in boxes):
                edge = ("out", center)
            elif abs(c - w0) < 0.12 or abs(c - w1) < 0.12:
                edge = edge or True  # вставка сменяет вставку, окно стоит на месте
        row = {"n": i, "t": round(t, 3), "scene_t": round(c, 3),
               **classify(e0, e1, accent, in_win and not edge, edge, a)}
        rows.append(row)
        pairs.append((row, img0, img1, e0, e1))
        mark = {True: "  ok ", False: "БРАК ", None: "  ?  "}[row["ok"]]
        extra = f"{row.get('ratio', 0):.2f}×  {row.get('deg', 0):.1f}°" if "ratio" in row else ""
        print(f"{mark} #{i:2d} {t:6.2f}s  {extra:14s} {row['verdict']}")

    # серии одной крупности подряд в полном кадре: больше трёх — брак (М-40)
    run = 0
    for r in rows:
        if r.get("krupnost") == "та же":
            run += 1
            r["seriya"] = run
            if run > SERIES_MAX:
                r.update(ok=False, klej="нет", verdict=f"{r['verdict']}; {run}-й стык одной крупности подряд")
        elif r["klej"] != "окно":
            run = 0
    judged = [r for r in rows if r["klej"] not in ("окно", "?")]
    bad = [r for r in judged if r["ok"] is False]
    summary = {
        "стыков": len(rows),
        "в полном кадре": len(judged),
        "не клеится": len(bad),
        "клей": {k: sum(1 for r in judged if r["klej"] == k) for k in ("эмоция", "точка и крупность", "звук", "нет")},
    }
    print(f"\nстыков {len(rows)}, в полном кадре {len(judged)}, не клеится {len(bad)}; клей: {summary['клей']}")
    if a.json:
        Path(a.json).write_text(json.dumps({"video": a.video, "offset": offset, "summary": summary, "cuts": rows,
                                            "porogi": {"eye_exact": a.eye_exact, "eye_ok": a.eye_ok,
                                                       "eye_bad": a.eye_bad,
                                                       "size_same": a.size_same, "size_two": a.size_two}},
                                           ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"записано: {a.json}")
    if a.sheet:
        make_sheet(a.sheet, pairs, size)
    return 0 if not bad else 2


def make_sheet(path: str, pairs, size) -> None:
    """Лист стыков: слева последний кадр до склейки, справа первый после; кружки — глаза."""
    cw = 150
    ch = int(round(cw * size[1] / size[0]))
    cells = []
    for row, img0, img1, e0, e1 in pairs:
        halves = []
        for img in (img0, img1):
            c = cv2.resize(img, (cw, ch)) if img is not None else np.zeros((ch, cw, 3), np.uint8)
            for e, color in ((e0, (0, 220, 255)), (e1, (60, 60, 255))):
                if e:
                    cv2.circle(c, (int(e["x"] * cw), int(e["y"] * ch)), 6, color, 2, cv2.LINE_AA)
            halves.append(c)
        pair = np.hstack(halves)
        strip = np.zeros((44, pair.shape[1], 3), np.uint8)
        color = {True: (80, 200, 80), False: (60, 60, 255), None: (0, 200, 255)}[row["ok"]]
        if row["klej"] == "окно":
            color = (160, 160, 160)
        head = f"#{row['n']} {row['t']:.2f}s"
        if "ratio" in row:
            head += f"  {row['ratio']:.2f}x {row['deg']:.1f}deg"
        cv2.putText(strip, head, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
        tail = {"эмоция": "EMOCIYA", "точка и крупность": "OK", "звук": "same size: voice only", "нет": "NE KLEITSYA",
                "окно": "okno", "?": "?"}[row["klej"]]
        if "krupnost" in row:
            tail += {"та же": "", "серая зона": " | grey zone", "ступень": "", "через ступень": " | 2 steps",
                     "пик": " | peak jump"}[row["krupnost"]]
            tail += {"точно": "", "на месте": "", "сдвиг": " | eye shift", "прыжок": " | EYE JUMP"}[row["tochka"]]
        cv2.putText(strip, tail, (4, 36), cv2.FONT_HERSHEY_SIMPLEX, 0.42, color, 1, cv2.LINE_AA)
        cells.append(np.vstack([pair, strip]))
    if not cells:
        return
    cols = 4
    blank = np.zeros_like(cells[0])
    while len(cells) % cols:
        cells.append(blank)
    sep = np.full((cells[0].shape[0], 8, 3), 30, np.uint8)
    rows = [np.hstack([x for c in cells[i: i + cols] for x in (c, sep)]) for i in range(0, len(cells), cols)]
    cv2.imwrite(path, np.vstack(rows))
    print(f"лист: {path}")


# ---------- main ----------

def main() -> int:
    p = argparse.ArgumentParser(description="стыки глазами режиссёра: крупность, точка внимания, эмоция")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("measure", help="где глаза на каждом куске речи")
    m.add_argument("video")
    m.add_argument("--edl")
    m.add_argument("--fps", type=float, default=5.0)
    m.add_argument("--json")

    pl = sub.add_parser("plan", help="крупности на склейках по ступеням и акцентам")
    pl.add_argument("--glaza", required=True)
    pl.add_argument("--spec", required=True)
    pl.add_argument("--scene", type=int, default=0)
    pl.add_argument("--akcenty")
    pl.add_argument("--from-src", action="store_true", help="секунды акцентов — исходника, перевести по edl")
    pl.add_argument("--min-sila", type=float, default=0.6, help="акцент слабее не даёт прыжка через ступень")
    pl.add_argument("--accent-reach", type=float, default=2.5,
                    help="акцент дальше от начала куска — не про этот стык: наезд ставится на начало фразы")
    pl.add_argument("--ladder", default=",".join(str(x) for x in LADDER))
    pl.add_argument("--write", action="store_true")

    au = sub.add_parser("audit", help="проверка стыков готового ролика")
    au.add_argument("video")
    au.add_argument("--edl", required=True)
    au.add_argument("--spec")
    au.add_argument("--scene", type=int, default=0)
    au.add_argument("--offset", type=float, help="секунда ролика, где начинается сцена; по умолчанию из спеки")
    au.add_argument("--akcenty")
    au.add_argument("--from-src", action="store_true")
    au.add_argument("--min-sila", type=float, default=0.5)
    au.add_argument("--accent-reach", type=float, default=2.5,
                    help="акцент дальше от стыка не про этот стык (и не дальше следующего стыка)")
    au.add_argument("--eye-exact", type=float, default=EYE_EXACT_DEG)
    au.add_argument("--eye-ok", type=float, default=EYE_OK_DEG)
    au.add_argument("--eye-bad", type=float, default=EYE_BAD_DEG)
    au.add_argument("--size-same", type=float, default=SIZE_SAME)
    au.add_argument("--size-two", type=float, default=SIZE_TWO)
    au.add_argument("--json")
    au.add_argument("--sheet")

    a = p.parse_args()
    return {"measure": cmd_measure, "plan": cmd_plan, "audit": cmd_audit}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
