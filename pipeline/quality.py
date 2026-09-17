"""
Замер качества исходника: что в нём реально испорчено и что чинить.

Зачем. Чистить всё подряд — ошибка: шумодав на чистом кадре съедает
детали, грейд на правильном балансе уводит кожу в синеву, компрессор
на хорошем звуке поднимает дыхание. Профессионал сначала смотрит, потом
трогает. Скрипт делает то же самое числами: меряет, сравнивает с порогом
и чинит только то, что вышло за порог.

    python quality.py clip.mp4                       отчёт по-русски
    python quality.py clip.mp4 --json q.json         плюс файл решений
    python quality.py clip.mp4 --fix out.mp4         починить только нужное

Все замеры делаются в масштабе вывода (короткая сторона 1080): зритель
видит шум и резкость именно в нём, а не в 4K исходника.

Главное отличие от наивного замера — оценка идёт по лицу, как у колориста.
Средняя яркость кадра и средний цвет кадра врут: тёмная сцена может быть
задумкой оператора, тёплая картинка — стилем. А вот лицо врать не может:
кожа должна лежать на линии телесного тона вектороскопа и быть экспонирована
в своём диапазоне. Если в кадре нет лица, флагуются только крайние случаи.

Пороги откалиброваны 16.09.2026 на пяти файлах: два сырых ролика владельца
(тёплый свет; шум в тенях на тёмной футболке), тот же рилс после чистки
и два стоковых клипа Pexels, один из них — намеренно тёмный и тёплый.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
from pathlib import Path

import cv2
import numpy as np
import sys
if hasattr(sys.stdout, "reconfigure"):  # консоль cp1251 роняла вывод со знаками «→», «×», «≈»
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:  # OpenCV 5 сыплет предупреждениями нового графа на каждый кадр
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except Exception:
    pass

YUNET = Path(__file__).resolve().parent.parent / "models" / "face_detection_yunet_2023mar.onnx"

# ---------- пороги ----------

TH = {
    # шум в тенях: сигма по Иммеркеру на ровных тёмных участках, уровни 0..255
    "noise_shadow": 1.6,
    # отклонение тона кожи от линии телесного тона, градусы
    "skin_hue": 11.0,
    # экспозиция лица, средняя яркость 0..1
    "face_lo": 0.38,
    "face_hi": 0.80,
    # без лица — только крайние случаи
    "luma_lo": 0.16,
    "luma_hi": 0.86,
    # точка чёрного: выше — «вымытая» картинка без глубоких теней
    "black_point": 0.09,
    # доля пересвеченных пикселей, после которой детали уже не вернуть
    "clip_hi": 0.02,
    # дисперсия лапласиана на лице в масштабе вывода
    "sharp": 30.0,
    # звук: шум в паузах (цифровая тишина не в счёт), dBFS, и речь/шум, dB
    "noise_floor": -55.0,
    "snr": 30.0,
    "clip_audio": 0.0005,
}

# Линия телесного тона на вектороскопе. В осях (Cb-128, Cr-128) это около
# 123°: кожа любого цвета лежит на ней, меняется только насыщенность.
SKIN_LINE = 123.0


# ---------- чтение ----------

def probe(src: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate:stream_side_data=rotation:format=duration,bit_rate",
         "-of", "json", src],
        capture_output=True, text=True, encoding="utf-8").stdout
    d = json.loads(out)
    st = d["streams"][0]
    rot = 0
    for sd in st.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = st["width"], st["height"]
    if abs(rot) % 180 == 90:
        w, h = h, w
    num, den = st.get("r_frame_rate", "30/1").split("/")
    return {
        "w": w, "h": h,
        "fps": round(float(num) / float(den or 1), 2),
        "sec": float(d["format"]["duration"]),
        "mbps": round(int(d["format"].get("bit_rate", 0) or 0) / 1e6, 1),
    }


def frame_at(src: str, t: float, w: int, h: int) -> np.ndarray:
    """Кадр в масштабе вывода: короткая сторона 1080."""
    if w <= h:
        ow, oh = 1080, int(round(h * 1080 / w / 2)) * 2
    else:
        oh, ow = 1080, int(round(w * 1080 / h / 2)) * 2
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
         "-vf", f"scale={ow}:{oh}", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(oh, ow, 3)


# ---------- замеры картинки ----------

def noise_in(gray: np.ndarray, mask: np.ndarray) -> float:
    """
    Шум по Иммеркеру (1996) на ровных участках маски. Текстура ткани и волос
    иначе читается как шум, и чистый кадр получает денойз зря.
    """
    g = gray.astype(np.float32)
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    resp = np.abs(cv2.filter2D(g, -1, k))
    grad = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
    sel = mask & (grad < np.percentile(grad[mask], 40) if mask.any() else mask)
    sel[:2, :] = sel[-2:, :] = False
    sel[:, :2] = sel[:, -2:] = False
    if sel.sum() < 1500:
        return 0.0
    return float(math.sqrt(math.pi / 2) / 6 * resp[sel].mean())


def face_box(bgr: np.ndarray) -> tuple[float, float, float, float] | None:
    """Самое крупное лицо: центр и размер в долях кадра."""
    small = cv2.resize(bgr, (bgr.shape[1] // 2, bgr.shape[0] // 2))
    H, W = small.shape[:2]
    det = cv2.FaceDetectorYN.create(str(YUNET), "", (W, H), 0.75, 0.3, 20)
    _, faces = det.detect(small)
    if faces is None or len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])[:4]
    return float((x + w / 2) / W), float((y + h / 2) / H), float(w / W), float(h / H)


def face_roi(img: np.ndarray, face, shrink: float = 0.55) -> np.ndarray:
    """Середина лица без волос, бороды и фона по краям рамки."""
    H, W = img.shape[:2]
    cx, cy, fw, fh = face
    w, h = fw * shrink, fh * shrink
    x0, x1 = int((cx - w / 2) * W), int((cx + w / 2) * W)
    y0, y1 = int((cy - h / 2 - fh * 0.05) * H), int((cy + h / 2 - fh * 0.05) * H)
    return img[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)]


def skin_hue(bgr: np.ndarray, face) -> tuple[float, float] | None:
    """Угол тона кожи на вектороскопе и его насыщенность."""
    roi = face_roi(bgr, face)
    if roi.size < 300:
        return None
    ycc = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb).astype(np.float32)
    y, cr, cb = ycc[..., 0], ycc[..., 1] - 128, ycc[..., 2] - 128
    ok = (y > 40) & (y < 235)  # тени и блики тон не показывают
    if ok.sum() < 150:
        return None
    x_, y_ = float(np.median(cb[ok])), float(np.median(cr[ok]))
    return math.degrees(math.atan2(y_, x_)), math.hypot(x_, y_)


def bright_neutral_cast(bgr: np.ndarray) -> float:
    """Запасной замер без лица: сдвиг по светлым нейтральным участкам, Lab."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    L, a, b = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    m = (L > np.percentile(L, 85)) & (np.hypot(a, b) < 28) & (L < 97)
    if m.sum() < 800:
        return 0.0
    return float(math.hypot(a[m].mean(), b[m].mean()))


def sharpness(bgr: np.ndarray, face) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    roi = face_roi(gray, face, 0.9) if face else gray[gray.shape[0] // 4: -gray.shape[0] // 4,
                                                          gray.shape[1] // 4: -gray.shape[1] // 4]
    return float(cv2.Laplacian(roi, cv2.CV_64F).var()) if roi.size else 0.0


# ---------- звук ----------

def audio_stats(src: str) -> dict | None:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"], capture_output=True).stdout
    if not raw:
        return None
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768.0
    win = 800  # 50 мс
    n = len(x) // win
    if n < 20:
        return None
    rms = np.sqrt((x[: n * win].reshape(n, win) ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    speech = float(np.percentile(db, 90))
    # Паузы: тише речи на 25 дБ. Цифровой ноль не шум — это шумоподавитель
    # беспроводного микрофона закрыл канал, по нему пол не меряется.
    quiet = db[(db < speech - 25) & (db > -90)]
    floor = float(np.median(quiet)) if len(quiet) >= 10 else None

    lufs = None
    log = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", src, "-vn", "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore").stderr
    m = re.findall(r"I:\s+(-?\d+(?:\.\d+)?) LUFS", log)
    if m:
        lufs = float(m[-1])
    return {
        "lufs": lufs,
        "noise_floor": round(floor, 1) if floor is not None else None,
        "speech": round(speech, 1),
        "snr": round(speech - floor, 1) if floor is not None else None,
        "digital_silence": round(float((db <= -90).mean()), 3),
        "clip": float((np.abs(x) >= 0.999).mean()),
    }


# ---------- решение ----------

def analyze(src: str, samples: int = 6) -> dict:
    info = probe(src)
    ts = [info["sec"] * (i + 0.5) / samples for i in range(samples)]
    acc: dict[str, list] = {k: [] for k in
                            ("luma", "black", "white", "clip_hi", "noise_sh", "face_luma",
                             "hue", "sat", "cast", "sharp", "faces")}
    for t in ts:
        f = frame_at(src, t, info["w"], info["h"])
        gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        y = gray.astype(np.float32) / 255
        acc["luma"].append(float(y.mean()))
        acc["black"].append(float(np.percentile(y, 1)))
        acc["white"].append(float(np.percentile(y, 99)))
        acc["clip_hi"].append(float((y > 0.98).mean()))
        acc["noise_sh"].append(noise_in(gray, (y > 0.04) & (y < 0.35)))
        acc["cast"].append(bright_neutral_cast(f))
        fb = face_box(f)
        if fb:
            acc["faces"].append(fb)
            fr = face_roi(y, fb)
            if fr.size:
                acc["face_luma"].append(float(fr.mean()))
            sh = skin_hue(f, fb)
            if sh:
                acc["hue"].append(sh[0])
                acc["sat"].append(sh[1])
        acc["sharp"].append(sharpness(f, fb))

    med = lambda v: round(float(np.median(v)), 3) if len(v) else None
    face = None
    if acc["faces"]:
        a = np.array(acc["faces"])
        face = {"x": med(a[:, 0]), "y": med(a[:, 1]), "w": med(a[:, 2]), "h": med(a[:, 3]),
                "found": f"{len(acc['faces'])} из {samples}"}

    m = {
        "luma": med(acc["luma"]), "black_point": med(acc["black"]), "white_point": med(acc["white"]),
        "clip_hi": med(acc["clip_hi"]), "noise_shadow": med(acc["noise_sh"]),
        "face_luma": med(acc["face_luma"]), "skin_hue": med(acc["hue"]), "skin_sat": med(acc["sat"]),
        "cast_neutral": med(acc["cast"]), "sharp": med(acc["sharp"]),
    }
    au = audio_stats(src)

    fixes, notes, vf, af = [], [], [], []

    # шум в тенях
    if m["noise_shadow"] and m["noise_shadow"] > TH["noise_shadow"]:
        k = min(1.0, (m["noise_shadow"] - TH["noise_shadow"]) / 2.5)
        l = round(3 + 4 * k, 1)
        fixes.append(f"шум в тенях {m['noise_shadow']} > {TH['noise_shadow']} — шумодав силы {l}")
        vf.append(f"hqdn3d={l}:{round(l*0.7,1)}:{round(l*1.4,1)}:{l}")

    # баланс — по коже, а без лица только по нейтральным светлым участкам и с запасом
    if m["skin_hue"] is not None:
        dev = m["skin_hue"] - SKIN_LINE
        if abs(dev) > TH["skin_hue"]:
            # угол больше линии — кожа уходит в жёлтый: остужаем; меньше — в розовый или синий
            warm = dev > 0
            temp = int(6500 + min(1600, abs(dev) * 75) * (1 if warm else -1))
            mix = round(min(0.9, 0.35 + abs(dev) / 40), 2)
            fixes.append(f"тон кожи {m['skin_hue']}° — отклонение {dev:+.0f}° от линии телесного тона "
                         f"({'в жёлтый' if warm else 'в розовый/синий'}) — температура {temp} K")
            vf.append(f"colortemperature=temperature={temp}:mix={mix}")
    elif m["cast_neutral"] and m["cast_neutral"] > 9:
        notes.append(f"лица нет, светлые участки со сдвигом {m['cast_neutral']} — если это не стиль, поправить руками")

    # экспозиция
    if m["face_luma"] is not None:
        if m["face_luma"] < TH["face_lo"]:
            g = round(1 + (TH["face_lo"] - m["face_luma"]) * 1.8, 2)
            fixes.append(f"лицо недоэкспонировано: {m['face_luma']} < {TH['face_lo']} — гамма {g}")
            vf.append(f"eq=gamma={g}")
        elif m["face_luma"] > TH["face_hi"]:
            g = round(1 - (m["face_luma"] - TH["face_hi"]) * 1.5, 2)
            fixes.append(f"лицо пересвечено: {m['face_luma']} > {TH['face_hi']} — гамма {g}")
            vf.append(f"eq=gamma={g}")
    elif m["luma"] < TH["luma_lo"] or m["luma"] > TH["luma_hi"]:
        notes.append(f"кадр без лица с яркостью {m['luma']} — проверить, задумка это или брак")

    # вымытые чёрные
    # светлая «воздушная» картинка без тёмных предметов — это стиль, а не вымытость
    if m["black_point"] > TH["black_point"] and m["luma"] < 0.50:
        lo = round(min(0.12, m["black_point"] * 0.8), 3)
        fixes.append(f"вымытые тени: точка чёрного {m['black_point']} > {TH['black_point']} — опустить чёрный")
        vf.append(f"colorlevels=rimin={lo}:gimin={lo}:bimin={lo}")

    if m["clip_hi"] > TH["clip_hi"]:
        notes.append(f"выбито {m['clip_hi']*100:.1f}% пикселей в белое — эти детали не вернуть, только переснять")

    if m["sharp"] is not None and m["sharp"] < TH["sharp"]:
        amt = round(min(1.1, 0.5 + (TH["sharp"] - m["sharp"]) / 40), 2)
        fixes.append(f"мягкое лицо: резкость {m['sharp']} < {TH['sharp']} — повышение резкости {amt}")
        vf.append(f"unsharp=5:5:{amt}:5:5:0.0")

    if au:
        if au["noise_floor"] is not None and (au["noise_floor"] > TH["noise_floor"] or au["snr"] < TH["snr"]):
            nf = int(max(-40, min(-20, au["noise_floor"] + 22)))
            fixes.append(f"шум в звуке: пол {au['noise_floor']} дБ, речь/шум {au['snr']} дБ — шумодав nf={nf}")
            af += [f"afftdn=nf={nf}", "highpass=f=80"]
        if au["clip"] > TH["clip_audio"]:
            notes.append(f"звук в клиппинге ({au['clip']*100:.2f}% сэмплов) — перегруз не лечится, только переписать")
        if au["noise_floor"] is None and au["digital_silence"] > 0.05:
            notes.append("в паузах цифровая тишина — микрофон сам глушит шум, чистить нечего")

    if not vf:
        notes.append("картинка в норме — не трогаем")
    if au and not af:
        notes.append("звук чистый — только мастеринг громкости")

    return {"src": src, "info": info, "metrics": m, "audio": au, "face": face,
            "thresholds": TH, "fixes": fixes, "notes": notes,
            "vf": ",".join(vf), "af": ",".join(af)}


def report(r: dict) -> str:
    i, m, au = r["info"], r["metrics"], r["audio"]
    lines = [
        f"{Path(r['src']).name}: {i['w']}×{i['h']}, {i['fps']} к/с, {i['sec']:.1f} с, {i['mbps']} Мбит/с",
        f"  картинка: яркость {m['luma']} · чёрный {m['black_point']} · шум в тенях {m['noise_shadow']} · "
        f"резкость лица {m['sharp']}",
        f"  лицо: яркость {m['face_luma']} · тон кожи {m['skin_hue']}° (линия {SKIN_LINE}°) · "
        f"насыщенность {m['skin_sat']}",
    ]
    if au:
        lines.append(f"  звук: {au['lufs']} LUFS · шум в паузах {au['noise_floor']} дБ · речь/шум {au['snr']} дБ · "
                     f"цифровая тишина {au['digital_silence']*100:.0f}%")
    if r["face"]:
        f = r["face"]
        lines.append(f"  где лицо: центр ({f['x']}, {f['y']}), размер {f['w']}×{f['h']} кадра, найдено {f['found']}")
    lines.append("  чинить:" if r["fixes"] else "  чинить нечего")
    lines += [f"    · {x}" for x in r["fixes"]]
    lines += [f"  заметка: {x}" for x in r["notes"]]
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser(description="замер качества и починка только нужного")
    p.add_argument("src")
    p.add_argument("--json")
    p.add_argument("--fix", help="собрать исправленный файл: 1080 по короткой стороне, 30 к/с")
    p.add_argument("--samples", type=int, default=6)
    a = p.parse_args()

    r = analyze(a.src, a.samples)
    print(report(r))
    if a.json:
        Path(a.json).write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    if a.fix:
        info = r["info"]
        scale = "scale=1080:-2" if info["w"] <= info["h"] else "scale=-2:1080"
        vf = ",".join(x for x in [scale, r["vf"], "fps=30"] if x)
        af = ",".join(x for x in [r["af"], "loudnorm=I=-14:TP=-1.5:LRA=11"] if x)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.src, "-vf", vf, "-af", af,
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                        "-c:a", "aac", "-b:a", "192k", a.fix], check=True)
        print(f"собрано: {a.fix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
