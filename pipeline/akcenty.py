"""
Карта эмоций: на каких словах речи стоят акценты, под которые монтаж ставит
склейку, наезд и тишину вставок.

Зачем. Владелец 16.09.2026: большую часть склеек держит эмоция, и ради её
акцента можно нарушить остальные правила. Значит, монтажу нужно знать, где
эмоция, — не «ролик энергичный», а конкретные слова. Смысловой отдел
отмечает их по тексту. Скрипт добавляет то, что слышно и видно: тон взлетел
и упал, перед словом пауза, брови пошли вверх, появилась улыбка.

    python pipeline/akcenty.py <исходник> --words slova.json [--tekst tekst.json] \
        [--edl edl.json] --json akcenty.json

slova.json — слова с секундами исходника: captions.json от transcribe.py или
align.py (блоки со словами t/s/e).

tekst.json — признаки смысла от montaj-smysl, в секундах исходника:
    {"priznaki": [{"t": 51.2, "slovo": "բազմապատկում", "priznaki": ["главная мысль", "обращение"]}]}
Без него скрипт ставит грубые признаки сам: цифры, «՞», «՛», «բայց / իսկ / այլ».

edl.json — таблица резки от jumpcut.py: секунды акцентов переводятся в секунды
ролика, слова из вырезанных кусков отбрасываются.

Всё считается по исходнику до вырезки пауз: пауза перед словом — сама по себе
признак акцента, а в чистовике её уже нет.

Как считается (плейбук, М-37; исследование 17.09.2026). Веса и пороги —
стартовые гипотезы, а не данные: калибровать по разметке владельца.
- голос: пик тона слова в полутонах от медианы говорящего, пик громкости,
  длительность на букву — z-оценки по ролику, среднее положительных;
  +0.5 за паузу 250 мс – 1.2 с перед словом (длиннее — перерыв между дублями);
  +0.5 за «пик и спад на 2+ полутона за 300 мс» после выделенного пика (z ≥ 1) —
  так в армянском звучит слово в фокусе. Подъём тона к концу слова без спада,
  когда речь идёт дальше, — ×0.5: это граница синтагмы;
- лицо (MediaPipe): скорость нарастания улыбки, брови, распахнутые глаза,
  скорость головы — z-оценки, среднее положительных;
- смысл: 0.75 за признак, «главная мысль» — за два, потолок 3.0: смысл без голоса
  и лица делает сильным моментом только главную мысль с подкреплением;
- сила = 0.4·голос + 0.3·лицо + 0.3·смысл. Сильный момент — два канала от 1.5
  или один от 2.5, между сильными не меньше 5 с ролика. Ожидаемо 2–5 на 30 с.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from difflib import SequenceMatcher
import subprocess
import sys
from pathlib import Path

import numpy as np

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MP_MODEL = ROOT / "models" / "face_landmarker.task"
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

SR = 16000
HOP = 160  # 10 мс
FACE_FPS = 10

VES = {"golos": 0.4, "lico": 0.3, "smysl": 0.3}
STRONG_ONE = 2.5
STRONG_TWO = 1.5
MIN_GAP = 5.0
PAUSE = 0.25
PAUSE_MAX = 1.2   # длиннее — это перерыв между дублями, а не пауза перед словом
FALL_ST = 2.0
FALL_PEAK_Z = 1.0  # спад засчитывается только после выделенного пика: спад в конце фразы есть почти везде
# «главная мысль» от смыслового отдела весит как два признака: иначе посыл ролика
# проигрывает любому вопросу с паузой
TEXT_WEIGHT = {"главная мысль": 2}

CONTRAST = {"բայց", "իսկ", "սակայն", "այլ"}


# ---------- входы ----------

def load_words(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    blocks = data if isinstance(data, list) else (data.get("blocks") or data.get("captions") or [])
    words = [{"t": w["t"], "s": float(w["s"]), "e": float(w["e"])} for b in blocks for w in b.get("words", [])]
    return sorted(words, key=lambda w: w["s"])


def load_edl(path: str | None) -> list[dict] | None:
    return json.loads(Path(path).read_text(encoding="utf-8"))["segments"] if path else None


def to_out(t: float, segs: list[dict] | None) -> float | None:
    if segs is None:
        return t
    for s in segs:
        a, b = s["src"]
        o0, o1 = s["out"]
        if a <= t <= b:
            return o0 + (t - a) * (o1 - o0) / max(b - a, 1e-6)
    return None


# ---------- голос ----------

def read_audio(src: str) -> np.ndarray:
    raw = subprocess.run([FFMPEG, "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "s16le", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float32) / 32768


def pitch_track(y: np.ndarray, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
    """Тон в полутонах от медианы говорящего; NaN — нет голоса."""
    import librosa

    a, b = max(int(t0 * SR), 0), min(int(t1 * SR), len(y))
    f0, _, _ = librosa.pyin(y[a:b], fmin=65, fmax=420, sr=SR, frame_length=1024, hop_length=HOP)
    times = a / SR + np.arange(len(f0)) * HOP / SR
    med = np.nanmedian(f0) if np.any(~np.isnan(f0)) else 1.0
    return times, 12 * np.log2(f0 / med)


def loudness(y: np.ndarray) -> np.ndarray:
    n = len(y) // HOP
    rms = np.sqrt((y[: n * HOP].reshape(n, HOP) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms)


def voice_features(words: list[dict], times: np.ndarray, st: np.ndarray, db: np.ndarray) -> list[dict]:
    out = []
    for i, w in enumerate(words):
        s, e = w["s"], w["e"]
        inside = (times >= s) & (times <= e)
        seg, seg_t = st[inside], times[inside]
        voiced = ~np.isnan(seg)
        f0_peak, fall, edge = np.nan, False, False
        if voiced.any():
            k = int(np.nanargmax(seg))
            f0_peak, tp = float(seg[k]), float(seg_t[k])
            after = (times > tp) & (times <= tp + 0.3) & ~np.isnan(st)
            fall = bool(after.any() and np.min(st[after]) <= f0_peak - FALL_ST)
            nxt = words[i + 1]["s"] if i + 1 < len(words) else None
            continues = nxt is not None and nxt - e < 0.15
            edge = tp >= e - 0.08 and continues and not fall
        a, b = int(s * 100), max(int(e * 100), int(s * 100) + 1)
        piece = db[a:b] if a < len(db) else db[-1:]
        letters = len(re.sub(r"[^\w]", "", w["t"])) or 1
        out.append({
            "f0": f0_peak,
            "db": float(np.max(piece)) if len(piece) else np.nan,
            "dur": (e - s) / letters,
            "pause": s - words[i - 1]["e"] if i > 0 else 0.0,
            "fall": fall,
            "edge": edge,
        })
    return out


# ---------- лицо ----------

def video_size(src: str) -> tuple[int, int]:
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "json", src],
                         capture_output=True, text=True, encoding="utf-8").stdout
    s = json.loads(out)["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    rot = next((abs(int(d.get("rotation", 0))) for d in s.get("side_data_list", []) if "rotation" in d), 0)
    return (h, w) if rot in (90, 270) else (w, h)


def face_track(src: str, t0: float, t1: float) -> dict | None:
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
    except Exception:
        return None
    if not MP_MODEL.exists():
        return None
    sw, sh = video_size(src)
    w = 360
    h = int(round(w * sh / sw / 2) * 2)
    raw = subprocess.run([FFMPEG, "-v", "error", "-ss", f"{max(t0, 0):.3f}", "-t", f"{t1 - t0:.3f}", "-i", src,
                          "-vf", f"fps={FACE_FPS},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    frames = np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)
    opts = vision.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(MP_MODEL)),
                                        output_face_blendshapes=True, num_faces=1)
    lm = vision.FaceLandmarker.create_from_options(opts)
    rows = {"t": [], "smile": [], "brow": [], "wide": [], "nose": []}
    for i in range(n):
        r = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(frames[i])))
        rows["t"].append(max(t0, 0) + i / FACE_FPS)
        if not r.face_blendshapes:
            for k in ("smile", "brow", "wide"):
                rows[k].append(np.nan)
            rows["nose"].append((np.nan, np.nan))
            continue
        b = {c.category_name: c.score for c in r.face_blendshapes[0]}
        rows["smile"].append((b["mouthSmileLeft"] + b["mouthSmileRight"]) / 2)
        rows["brow"].append(max(b["browInnerUp"], (b["browOuterUpLeft"] + b["browOuterUpRight"]) / 2))
        rows["wide"].append((b["eyeWideLeft"] + b["eyeWideRight"]) / 2)
        p = r.face_landmarks[0][1]
        rows["nose"].append((p.x, p.y * h / w))
    t = np.array(rows["t"])
    nose = np.array(rows["nose"], float)
    speed = np.r_[0.0, np.hypot(*np.diff(nose, axis=0).T) * FACE_FPS] if len(nose) > 1 else np.zeros(len(t))
    return {"t": t, "smile": np.array(rows["smile"]), "brow": np.array(rows["brow"]),
            "wide": np.array(rows["wide"]), "head": speed}


def face_features(words: list[dict], tr: dict | None) -> list[dict]:
    if tr is None:
        return [{"smile": np.nan, "brow": np.nan, "wide": np.nan, "head": np.nan} for _ in words]
    lag = int(0.4 * FACE_FPS)
    rise = np.full(len(tr["t"]), np.nan)
    rise[lag:] = tr["smile"][lag:] - tr["smile"][:-lag]
    out = []
    for w in words:
        m = (tr["t"] >= w["s"] - 0.2) & (tr["t"] <= w["e"] + 0.3)

        def peak(x):
            v = x[m]
            return float(np.nanmax(v)) if v.size and np.any(~np.isnan(v)) else np.nan

        out.append({"smile": peak(rise), "brow": peak(tr["brow"]), "wide": peak(tr["wide"]), "head": peak(tr["head"])})
    return out


# ---------- смысл ----------

def text_features(words: list[dict], tekst: str | None) -> list[list[str]]:
    feats: list[list[str]] = [[] for _ in words]
    if tekst:
        items = json.loads(Path(tekst).read_text(encoding="utf-8")).get("priznaki", [])
        for it in items:
            t = float(it["t"])
            near = [k for k in range(len(words)) if abs((words[k]["s"] + words[k]["e"]) / 2 - t) <= 1.0]
            if not near:
                continue
            # слово ищется по написанию рядом со временем: разметчик ставит секунду
            # на глаз, а распознавание пишет армянское слово с ошибками
            want = re.sub(r"[^\w]", "", str(it.get("slovo", "")).split()[0].lower()) if it.get("slovo") else ""

            def score(k):
                got = re.sub(r"[^\w]", "", words[k]["t"].lower())
                like = SequenceMatcher(None, want, got).ratio() if want else 0.0
                return (like >= 0.5, like, -abs((words[k]["s"] + words[k]["e"]) / 2 - t))

            feats[max(near, key=score)] += list(it.get("priznaki", []))
        return feats
    for i, w in enumerate(words):
        low = re.sub(r"[^\w՞՛]", "", w["t"].lower())
        if re.search(r"\d", low):
            feats[i].append("число")
        if "՞" in w["t"]:
            feats[i].append("вопрос")
        if "՛" in w["t"]:
            feats[i].append("повеление")
        if low.replace("՞", "").replace("՛", "") in CONTRAST:
            feats[i].append("контраст")
    return feats


# ---------- сведение ----------

def zscore(vals) -> np.ndarray:
    x = np.array(vals, float)
    ok = ~np.isnan(x)
    out = np.zeros_like(x)
    if ok.sum() >= 3:
        sd = x[ok].std() or 1.0
        out[ok] = (x[ok] - x[ok].mean()) / sd
    return out


def mean_pos(*zs: float) -> float:
    pos = [z for z in zs if z > 0]
    return float(np.mean(pos)) if pos else 0.0


def main() -> int:
    p = argparse.ArgumentParser(description="карта эмоций: акценты речи по голосу, лицу и смыслу")
    p.add_argument("src", help="исходник: видео со звуком (для лица) или звук")
    p.add_argument("--words", required=True, help="слова с секундами исходника (captions.json)")
    p.add_argument("--tekst", help="признаки смысла от montaj-smysl")
    p.add_argument("--edl", help="edl.json — перевести в секунды ролика и отбросить вырезанное")
    p.add_argument("--no-face", action="store_true", help="без лица: только голос и смысл")
    p.add_argument("--gap", type=float, default=MIN_GAP, help="между сильными моментами не меньше, с ролика")
    p.add_argument("--top", type=int, default=15, help="сколько кандидатов показать")
    p.add_argument("--json")
    a = p.parse_args()

    words = load_words(a.words)
    segs = load_edl(a.edl)
    if not words:
        print("слов нет")
        return 1
    t0, t1 = words[0]["s"] - 0.5, words[-1]["e"] + 0.5

    y = read_audio(a.src)
    print(f"слов {len(words)}; тон и громкость {t0:.1f}–{t1:.1f} с…")
    times, st = pitch_track(y, t0, t1)
    vf = voice_features(words, times, st, loudness(y))
    print("лицо…" if not a.no_face else "лицо пропущено")
    ff = face_features(words, None if a.no_face else face_track(a.src, t0, t1))
    tf = text_features(words, a.tekst)

    zf, zd, zu = zscore([v["f0"] for v in vf]), zscore([v["db"] for v in vf]), zscore([v["dur"] for v in vf])
    zs, zb, zw, zh = (zscore([f[k] for f in ff]) for k in ("smile", "brow", "wide", "head"))

    rows = []
    for i, w in enumerate(words):
        why = []
        golos = mean_pos(zf[i], zd[i], zu[i])
        if zf[i] >= 1.5:
            why.append(f"тон +{zf[i]:.1f}σ")
        if zd[i] >= 1.5:
            why.append(f"громче +{zd[i]:.1f}σ")
        if zu[i] >= 1.5:
            why.append(f"протянуто +{zu[i]:.1f}σ")
        if PAUSE <= vf[i]["pause"] <= PAUSE_MAX:
            golos += 0.5
            why.append(f"пауза {vf[i]['pause'] * 1000:.0f} мс")
        if vf[i]["fall"] and zf[i] >= FALL_PEAK_Z:
            golos += 0.5
            why.append("пик и спад тона")
        if vf[i]["edge"]:
            golos *= 0.5
            why.append("подъём на краю — граница")
        lico = mean_pos(zs[i], zb[i], zw[i], zh[i])
        for z, name in ((zs[i], "улыбка"), (zb[i], "брови"), (zw[i], "глаза"), (zh[i], "голова")):
            if z >= 1.5:
                why.append(f"{name} +{z:.1f}σ")
        smysl = min(3.0, 0.75 * sum(TEXT_WEIGHT.get(x, 1) for x in tf[i]))
        why += tf[i]
        sila = VES["golos"] * golos + VES["lico"] * lico + VES["smysl"] * smysl
        chans = {"golos": round(golos, 2), "lico": round(lico, 2), "smysl": smysl}
        strong = sum(1 for v in chans.values() if v >= STRONG_TWO) >= 2 or max(chans.values()) >= STRONG_ONE
        mid = (w["s"] + w["e"]) / 2
        t_out = to_out(mid, segs)
        if t_out is None:
            continue  # слово вырезано — акцента в ролике нет
        rows.append({"t": round(t_out, 3), "t_src": round(w["s"], 3), "slovo": w["t"], "sila_raw": round(sila, 3),
                     "sila": round(min(1.0, sila / 2.0), 3), "kanaly": chans, "silnyy": strong, "pochemu": why})

    picked: list[dict] = []
    for r in sorted((r for r in rows if r["silnyy"]), key=lambda r: -r["sila_raw"]):
        if all(abs(r["t"] - q["t"]) >= a.gap for q in picked):
            picked.append(r)
    picked.sort(key=lambda r: r["t"])
    for r in picked:
        r["chto"] = f"{r['slovo']} — {', '.join(r['pochemu']) or 'сила'}"

    dur = (rows[-1]["t"] - rows[0]["t"]) if rows else 0
    print(f"\nсильных моментов {len(picked)} на {dur:.0f} с ролика (ожидаемо 2–5 на 30 с):")
    for r in picked:
        print(f"  {r['t']:6.2f}s (исх. {r['t_src']:6.2f})  сила {r['sila']:.2f}  {r['chto']}")
    cand = sorted(rows, key=lambda r: -r["sila_raw"])[: a.top]
    print("\nкандидаты по силе:")
    for r in cand:
        mark = "★" if r in picked else " "
        print(f" {mark} {r['t']:6.2f}s  {r['sila_raw']:.2f}  голос {r['kanaly']['golos']:.1f} лицо {r['kanaly']['lico']:.1f} "
              f"смысл {r['kanaly']['smysl']:.1f}  {r['slovo']}  {'; '.join(r['pochemu'])}")

    if a.json:
        Path(a.json).write_text(json.dumps({
            "istochnik": a.src, "slova": a.words, "tekst": a.tekst, "edl": a.edl,
            "vesa": VES, "porogi": {"odin_kanal": STRONG_ONE, "dva_kanala": STRONG_TWO, "gap": a.gap,
                                    "pauza": PAUSE, "spad_tona": FALL_ST},
            "akcenty": picked, "kandidaty": cand,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nзаписано: {a.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
