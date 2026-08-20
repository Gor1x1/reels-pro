# -*- coding: utf-8 -*-
r"""Машинный портрет ролика: ритм планов, текст на экране, звуковые акценты.

    python shotstats.py <файл.mp4> [--out папка] [--ocr]

Отвечает на вопросы, которые глазом считать долго и неточно:
сколько в ролике планов, по сколько секунд каждый, где ускорение,
в какой трети экрана стоит титр и сколько он держится, где всплески
звука. Всё это — прямые указания оператору и монтажёру.

На выходе рядом с видео:
    <имя>.shots.json     цифры машинно
    <имя>-планы.jpg      контактный лист: первый кадр каждого плана

Склейки ловятся по разнице гистограмм соседних кадров. Резкий монтаж
берётся уверенно, плавные переходы (кроссфейд, вайп) считаются одним
планом — в короткой вертикальной рекламе их почти не бывает.

`--ocr` включает распознавание титров, если установлен easyocr или
pytesseract. Без флага скрипт всё равно находит текстовые области
и их положение — сам текст читает агент по контактному листу.
"""
import json
import os
import subprocess
import sys

try:
    import cv2
    import numpy as np
except ImportError:
    sys.exit("нет OpenCV: python -m pip install opencv-python numpy")

# Порог смены плана: доля несовпадения гистограмм соседних кадров.
# 0.35 отобрано на вертикальной рекламе — ниже ловит дрожание камеры,
# выше пропускает склейки внутри одной локации.
CUT_THRESHOLD = 0.35
MIN_SHOT_SEC = 0.3          # короче — это мигание, а не план
SAMPLE_FPS = 10             # кадров в секунду на анализ, больше не нужно


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def hist(frame):
    small = cv2.resize(frame, (160, 284))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(h, h, 0, 1, cv2.NORM_MINMAX)
    return h


def text_zones(frame):
    """Где на экране стоит текст: верх / центр / низ и какую долю занимает.

    Классический приём: градиенты по X выделяют штрихи букв, морфология
    склеивает их в строки, дальше отбираем вытянутые прямоугольники.
    """
    h, w = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    joined = cv2.morphologyEx(bw, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (int(w * 0.06), 3)))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    zones = {"верх": 0.0, "центр": 0.0, "низ": 0.0}
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if ch < h * 0.012 or ch > h * 0.20:      # не строка текста
            continue
        if cw < w * 0.12 or cw / max(ch, 1) < 2.5:
            continue
        share = (cw * ch) / float(w * h)
        centre = y + ch / 2.0
        key = "верх" if centre < h / 3 else ("центр" if centre < 2 * h / 3 else "низ")
        zones[key] += share
    return zones


def audio_profile(path, duration):
    """Громкость по половинкам секунды — видно, где звуковые акценты."""
    if duration <= 0:
        return []
    cmd = ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000",
           "-f", "s16le", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True).stdout
    except FileNotFoundError:
        return []
    if not raw:
        return []
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    win = 4000                                   # 0.5 с при 8 кГц
    tail = len(a) - len(a) % win
    if tail <= 0:
        return []
    blocks = a[:tail].reshape(-1, win)
    rms = np.sqrt((blocks ** 2).mean(axis=1))
    peak = rms.max() or 1.0
    return [round(float(v / peak), 2) for v in rms]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    path = sys.argv[1]
    if not os.path.exists(path):
        sys.exit("нет файла: " + path)
    outdir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv \
        else os.path.dirname(os.path.abspath(path))
    want_ocr = "--ocr" in sys.argv
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(path))[0]

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        sys.exit("не открывается видео: " + path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    step = max(int(round(fps / SAMPLE_FPS)), 1)
    duration = probe_duration(path)

    cuts, firsts, zone_track = [0.0], [], []
    prev, idx, first_frame = None, 0, None
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % step == 0:
            t = idx / fps
            if first_frame is None:
                first_frame = frame.copy()
            h = hist(frame)
            if prev is not None:
                diff = 1.0 - float(cv2.compareHist(prev, h, cv2.HISTCMP_CORREL))
                if diff > CUT_THRESHOLD and t - cuts[-1] >= MIN_SHOT_SEC:
                    cuts.append(round(t, 2))
                    firsts.append((round(t, 2), frame.copy()))
            prev = h
            if len(zone_track) < 400:
                zone_track.append((round(t, 1), text_zones(frame)))
        idx += 1
    cap.release()

    ends = cuts[1:] + [round(duration, 2)]
    shots = [{"с": s, "по": e, "длина": round(e - s, 2)}
             for s, e in zip(cuts, ends) if e > s]
    lens = [s["длина"] for s in shots] or [duration]

    # текст на экране: доля кадров, где зона занята, и средняя площадь
    zone_share, zone_area = {}, {}
    for key in ("верх", "центр", "низ"):
        hits = [z[key] for _, z in zone_track if z[key] > 0.005]
        zone_share[key] = round(len(hits) / max(len(zone_track), 1), 2)
        zone_area[key] = round(sum(hits) / len(hits), 3) if hits else 0.0

    audio = audio_profile(path, duration)
    loud = [round(i * 0.5, 1) for i, v in enumerate(audio) if v > 0.8][:12]

    half = len(lens) // 2 or 1
    data = {
        "файл": os.path.basename(path),
        "длительность": round(duration, 2),
        "планов": len(shots),
        "ритм": {
            "средняя_длина_плана": round(sum(lens) / len(lens), 2),
            "медиана": round(sorted(lens)[len(lens) // 2], 2),
            "самый_короткий": round(min(lens), 2),
            "самый_длинный": round(max(lens), 2),
            "планов_в_первые_3_сек": sum(1 for s in shots if s["с"] < 3.0),
            "темп_первой_половины": round(sum(lens[:half]) / half, 2),
            "темп_второй_половины": round(sum(lens[half:]) / max(len(lens) - half, 1), 2),
        },
        "текст_на_экране": {
            "доля_кадров_с_текстом": zone_share,
            "средняя_площадь": zone_area,
            "держится_весь_ролик": {k: bool(v > 0.85) for k, v in zone_share.items()},
        },
        "звук": {"акценты_сек": loud, "профиль_громкости": audio[:120]},
        "планы": shots,
    }

    if want_ocr:
        data["титры"] = run_ocr(firsts, first_frame)

    # контактный лист: первый кадр каждого плана с подписью времени
    sheet = contact_sheet([(0.0, first_frame)] + firsts) if first_frame is not None else None
    sheet_path = os.path.join(outdir, base + "-планы.jpg")
    if sheet is not None:
        # cv2.imwrite на Windows не понимает кириллицу в пути: кодируем
        # в память и пишем обычным файловым вызовом.
        ok, buf = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 82])
        if ok:
            with open(sheet_path, "wb") as f:
                f.write(buf.tobytes())
        else:
            sheet = None

    json_path = os.path.join(outdir, base + ".shots.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    def p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((s + "\n").encode("utf-8"))

    r = data["ритм"]
    p("%s · %.1f с · планов: %d" % (data["файл"], data["длительность"], data["планов"]))
    p("средний план %.2f с (медиана %.2f) · в первые 3 сек планов: %d"
      % (r["средняя_длина_плана"], r["медиана"], r["планов_в_первые_3_сек"]))
    p("темп: первая половина %.2f с, вторая %.2f с"
      % (r["темп_первой_половины"], r["темп_второй_половины"]))
    for k, v in zone_share.items():
        if v > 0.05:
            p("текст %s: в %d%% кадров, площадь %.1f%%"
              % (k, int(v * 100), zone_area[k] * 100))
    if loud:
        p("звуковые акценты на секундах: " + ", ".join(str(x) for x in loud))
    p("записано: " + json_path + (" и " + sheet_path if sheet is not None else ""))


def contact_sheet(frames, cols=5, cell_w=216):
    """Первые кадры планов одной картинкой — агент смотрит её глазами."""
    tiles = []
    for t, fr in frames[:30]:
        if fr is None:
            continue
        h, w = fr.shape[:2]
        cell_h = int(cell_w * h / w)
        tile = cv2.resize(fr, (cell_w, cell_h))
        cv2.rectangle(tile, (0, 0), (cell_w, 22), (0, 0, 0), -1)
        cv2.putText(tile, "%.1fs" % t, (6, 16), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    if not tiles:
        return None
    ch = tiles[0].shape[0]
    rows = []
    for i in range(0, len(tiles), cols):
        row = tiles[i:i + cols]
        while len(row) < cols:
            row.append(np.zeros_like(tiles[0]))
        rows.append(np.hstack([cv2.resize(t, (cell_w, ch)) for t in row]))
    return np.vstack(rows)


def run_ocr(firsts, first_frame):
    """Титры дословно — если в системе есть OCR-движок.

    Ставится отдельно и не входит в обязательные требования: без него
    текст читает агент по контактному листу, что для коротких титров
    даже надёжнее.
    """
    frames = [f for _, f in ([(0.0, first_frame)] + firsts)[:12] if f is not None]
    try:
        import easyocr
        reader = easyocr.Reader(["ru", "en"], gpu=False, verbose=False)
        return [{"кадр": i, "текст": [t for _, t, c in reader.readtext(f) if c > 0.4]}
                for i, f in enumerate(frames)]
    except ImportError:
        pass
    try:
        import pytesseract
        return [{"кадр": i,
                 "текст": [l for l in pytesseract.image_to_string(
                     cv2.cvtColor(f, cv2.COLOR_BGR2RGB), lang="rus+eng").split("\n") if l.strip()]}
                for i, f in enumerate(frames)]
    except ImportError:
        return {"нет": "OCR-движок не установлен: pip install easyocr "
                       "(или pytesseract + бинарник tesseract). "
                       "Без него титры читает агент по контактному листу."}


if __name__ == "__main__":
    main()
