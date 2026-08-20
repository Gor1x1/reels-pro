"""
Разбор исходников перед монтажом. Агент не режет вслепую: сначала смотрит,
что в файлах, потом составляет план по таймкодам.

Отдаёт JSON и раскладку кадров — по ним видно, где что происходит,
где речь, где пауза и где режиссёр сменил план.

    python scan.py probe   <файлы...>              — что за файлы
    python scan.py audio   <файл>                  — тишина и громкость по времени
    python scan.py cuts    <файл>                  — где меняется картинка
    python scan.py frames  <файл> --every 1.0      — кадры на просмотр
    python scan.py full    <файлы...> --out map.json

`full` собирает всё вместе: это то, что запускается перед сборкой ролика.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Частота, из которой считается длина окна для карты громкости. Реальная
# частота файла может отличаться — окно тогда просто чуть другой длины,
# на выводе это не сказывается, потому что время берётся из pts.
SR_ASSUMED = 48000


def run(cmd: list[str]) -> str:
    """ffmpeg пишет диагностику в stderr, поэтому берём оба потока."""
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


# --------------------------------------------------------------------------- probe


def probe(path: str) -> dict:
    out = run(
        [
            FFPROBE, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", path,
        ]
    )
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"file": path, "error": "не читается как медиафайл"}

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})

    def fps(stream: dict | None) -> float:
        if not stream:
            return 0.0
        num, _, den = (stream.get("r_frame_rate") or "0/1").partition("/")
        try:
            return round(int(num) / max(int(den), 1), 3)
        except ValueError:
            return 0.0

    w = int(v.get("width", 0)) if v else 0
    h = int(v.get("height", 0)) if v else 0

    return {
        "file": path,
        "name": Path(path).name,
        "duration": round(float(fmt.get("duration", 0) or 0), 3),
        "width": w,
        "height": h,
        # вертикаль, горизонталь или квадрат — от этого зависит кадрирование
        "orientation": "vertical" if h > w else ("square" if h == w else "horizontal"),
        "fps": fps(v),
        "vcodec": v.get("codec_name") if v else None,
        "acodec": a.get("codec_name") if a else None,
        "has_audio": a is not None,
        "size_mb": round(float(fmt.get("size", 0) or 0) / 1024 / 1024, 2),
    }


# --------------------------------------------------------------------------- звук


def silences(path: str, noise_db: float = -34.0, min_dur: float = 0.35) -> list[dict]:
    """
    Паузы в речи. Порог намеренно выше уровня закадровой подсказки: она тише
    основной речи на 10–12 dB, и с порогом -34 dB её слышно как тишину.
    """
    out = run(
        [
            FFMPEG, "-hide_banner", "-nostats", "-i", path,
            "-af", f"silencedetect=noise={noise_db}dB:d={min_dur}",
            "-f", "null", "-",
        ]
    )
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", out)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", out)]
    res = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        res.append({"start": round(s, 3), "end": round(e, 3) if e else None,
                    "dur": round(e - s, 3) if e else None})
    return res


def loudness(path: str, step: float = 0.5) -> dict:
    """Средняя и пиковая громкость плюс грубая карта по времени."""
    out = run([FFMPEG, "-hide_banner", "-nostats", "-i", path, "-af", "volumedetect", "-f", "null", "-"])
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", out)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", out)

    # Громкость по времени: по ней видно, где человек говорит, а где фон.
    # Время берётся из pts самого ffmpeg, а не считается шагом — при
    # переменном размере кадра расчётный шаг уезжает на длинном файле.
    lvl = run(
        [
            FFMPEG, "-hide_banner", "-nostats", "-i", path,
            "-af", f"asetnsamples=n={int(SR_ASSUMED * step)},astats=metadata=1:reset=1,"
                   f"ametadata=print:key=lavfi.astats.Overall.RMS_level",
            "-f", "null", "-",
        ]
    )
    curve = []
    pending_t: float | None = None
    for line in lvl.splitlines():
        m_pts = re.search(r"pts_time:([\d.]+)", line)
        if m_pts:
            pending_t = float(m_pts.group(1))
            continue
        m_db = re.search(r"lavfi\.astats\.Overall\.RMS_level=(-?[\d.]+|-?inf)", line)
        if m_db and pending_t is not None:
            raw = m_db.group(1)
            db = -99.0 if "inf" in raw else round(float(raw), 1)
            curve.append({"t": round(pending_t, 2), "db": db})
            pending_t = None

    return {
        "mean_db": float(mean.group(1)) if mean else None,
        "peak_db": float(peak.group(1)) if peak else None,
        "curve": curve,
    }


# --------------------------------------------------------------------------- картинка


def cuts(path: str, threshold: float = 0.35) -> list[float]:
    """
    Секунды, где картинка резко меняется. В готовых рилсах это чужие склейки —
    резать надо по ним, иначе кусок начнётся с середины чужого плана.
    """
    out = run(
        [
            FFMPEG, "-hide_banner", "-nostats", "-i", path,
            "-filter_complex", f"select='gt(scene,{threshold})',metadata=print",
            "-f", "null", "-",
        ]
    )
    return [round(float(x), 3) for x in re.findall(r"pts_time:([\d.]+)", out)]


def frames(path: str, out_dir: str, every: float = 1.0, width: int = 480) -> list[str]:
    """Кадры на просмотр. Ими агент понимает, что происходит в файле."""
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    stem = Path(path).stem
    pattern = str(d / f"{stem}-%03d.jpg")
    run(
        [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", path,
            "-vf", f"fps=1/{every},scale={width}:-2",
            "-q:v", "4", pattern,
        ]
    )
    return sorted(str(p) for p in d.glob(f"{stem}-*.jpg"))


# --------------------------------------------------------------------------- всё вместе


def full(paths: list[str], frames_dir: str | None, every: float) -> dict:
    result = {"files": []}
    for p in paths:
        info = probe(p)
        if "error" in info:
            result["files"].append(info)
            continue
        info["silences"] = silences(p) if info["has_audio"] else []
        info["loudness"] = loudness(p) if info["has_audio"] else {}
        info["cuts"] = cuts(p)
        if frames_dir:
            info["frames"] = frames(p, frames_dir, every)
        result["files"].append(info)

    result["total_duration"] = round(sum(f.get("duration", 0) for f in result["files"]), 2)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description="разбор исходников для монтажа")
    ap.add_argument("cmd", choices=["probe", "audio", "cuts", "frames", "full"])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", help="куда положить JSON")
    ap.add_argument("--frames-dir", help="куда положить кадры")
    ap.add_argument("--every", type=float, default=1.0, help="шаг кадров, сек")
    args = ap.parse_args()

    if args.cmd == "probe":
        data = {"files": [probe(p) for p in args.paths]}
    elif args.cmd == "audio":
        data = {p: {"silences": silences(p), "loudness": loudness(p)} for p in args.paths}
    elif args.cmd == "cuts":
        data = {p: cuts(p) for p in args.paths}
    elif args.cmd == "frames":
        d = args.frames_dir or "frames"
        data = {p: frames(p, d, args.every) for p in args.paths}
    else:
        data = full(args.paths, args.frames_dir, args.every)

    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"записано: {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
