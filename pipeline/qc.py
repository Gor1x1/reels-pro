"""
Техническая проверка готового ролика. Числа, а не мнение: не прошёл —
до просмотра глазами дело не доходит.

    python qc.py final.mp4
    python qc.py final.mp4 --json qc.json

Пороги взяты из требований площадок и одинаковы для всех семи сетей.
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

WANT_W, WANT_H = 1080, 1920
MIN_SEC, MAX_SEC = 15.0, 40.0
WANT_LUFS, LUFS_TOL = -14.0, 1.5
MAX_SILENCE = 1.5


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return (p.stdout or "") + (p.stderr or "")


def check(path: str, dark_text: bool = False) -> dict:
    checks: list[dict] = []

    def add(name: str, ok: bool, got: str, want: str) -> None:
        checks.append({"проверка": name, "ок": ok, "получено": got, "нужно": want})

    raw = run([FFPROBE, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"файл": path, "открывается": False, "проверки": [], "вердикт": "БРАК"}

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(data.get("format", {}).get("duration", 0) or 0)

    if not v:
        return {"файл": path, "открывается": False, "проверки": [], "вердикт": "БРАК"}

    w, h = int(v.get("width", 0)), int(v.get("height", 0))
    add("разрешение", w == WANT_W and h == WANT_H, f"{w}x{h}", f"{WANT_W}x{WANT_H}")

    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    fps = round(int(num) / max(int(den), 1), 2) if num.isdigit() else 0
    add("частота кадров", 24 <= fps <= 60, f"{fps} fps", "24–60 fps")

    add("длительность", MIN_SEC <= dur <= MAX_SEC, f"{dur:.1f} сек", f"{MIN_SEC:.0f}–{MAX_SEC:.0f} сек")
    add("звуковая дорожка", a is not None, "есть" if a else "нет", "есть")

    if a:
        out = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                   "-af", "loudnorm=I=-14:TP=-1.5:print_format=summary", "-f", "null", "-"])
        m = re.search(r"Input Integrated:\s*(-?[\d.]+) LUFS", out)
        lufs = float(m.group(1)) if m else None
        add(
            "громкость",
            lufs is not None and abs(lufs - WANT_LUFS) <= LUFS_TOL,
            f"{lufs} LUFS" if lufs is not None else "не измерено",
            f"{WANT_LUFS} ± {LUFS_TOL} LUFS",
        )

        sil = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                   "-af", f"silencedetect=noise=-50dB:d={MAX_SILENCE}", "-f", "null", "-"])
        longest = [float(x) for x in re.findall(r"silence_duration:\s*([\d.]+)", sil)]
        worst = max(longest) if longest else 0.0
        add("паузы", worst < MAX_SILENCE, f"{worst:.1f} сек", f"< {MAX_SILENCE} сек")

    # чёрные кадры: пустой кадр в начале — самая заметная поломка сборки
    black = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                 "-vf", "blackdetect=d=0.3:pix_th=0.10", "-f", "null", "-"])
    blacks = re.findall(r"black_start:([\d.]+)", black)
    add("чёрные кадры", not blacks, f"{len(blacks)} шт", "нет")

    # Замершая картинка: признак того, что клип кончился раньше сцены.
    # Порог 2.5 с намеренно мягкий — статичная плашка CTA держится 3 секунды
    # и это норма, а вот зависший на две с половиной секунды клип — брак.
    freeze = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                  "-vf", "freezedetect=n=-58dB:d=2.5", "-f", "null", "-"])
    freezes = re.findall(r"freeze_start:\s*([\d.]+)", freeze)
    add(
        "замершие кадры",
        not freezes,
        f"{len(freezes)} шт" + (f" (с {', '.join(freezes[:3])} с)" if freezes else ""),
        "нет",
    )

    # Читаемость субтитров: белые буквы пропадают на светлом фоне, тёмные —
    # на тёмном. Что именно проверять, зависит от стиля: `soft-cream`
    # единственный со светлой плашкой и тёмным текстом, для него всё наоборот.
    band = run([FFMPEG, "-hide_banner", "-nostats", "-i", path,
                "-vf", f"crop={WANT_W}:{int(WANT_H * 0.14)}:0:{int(WANT_H * 0.62)},"
                       f"signalstats,metadata=print:key=lavfi.signalstats.YAVG",
                "-f", "null", "-"])
    yavgs = [float(x) for x in re.findall(r"lavfi\.signalstats\.YAVG=([\d.]+)", band)]
    if yavgs:
        if dark_text:
            risky = sum(1 for y in yavgs if y < 70) / len(yavgs)
            add("фон под субтитрами", risky < 0.35, f"тёмный на {risky * 100:.0f}% кадров", "меньше 35%")
        else:
            risky = sum(1 for y in yavgs if y > 165) / len(yavgs)
            add("фон под субтитрами", risky < 0.35, f"светлый на {risky * 100:.0f}% кадров", "меньше 35%")

    failed = [c for c in checks if not c["ок"]]
    return {
        "файл": Path(path).name,
        "открывается": True,
        "проверки": checks,
        "провалено": len(failed),
        "вердикт": "ПРОШЁЛ" if not failed else "БРАК",
    }


# стили со светлой плашкой и тёмным текстом — у них риск обратный
DARK_TEXT_STYLES = {"soft-cream"}


def style_of(spec_path: Path) -> str:
    if not spec_path.exists():
        return ""
    try:
        return json.loads(spec_path.read_text(encoding="utf-8-sig")).get("style", "")
    except (json.JSONDecodeError, OSError):
        return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="техническая проверка ролика")
    ap.add_argument("path")
    ap.add_argument("--json", help="куда записать отчёт")
    ap.add_argument("--spec", help="спека ролика — из неё берётся стиль")
    args = ap.parse_args()

    spec_path = Path(args.spec) if args.spec else Path(__file__).resolve().parent.parent / "src" / "spec.json"
    res = check(args.path, style_of(spec_path) in DARK_TEXT_STYLES)

    print(f"\n{res['файл']} — {res['вердикт']}\n")
    for c in res["проверки"]:
        mark = "  ок  " if c["ок"] else " БРАК "
        print(f"[{mark}] {c['проверка']:<18} {c['получено']:<16} нужно: {c['нужно']}")
    print()

    if args.json:
        Path(args.json).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0 if res["вердикт"] == "ПРОШЁЛ" else 1


if __name__ == "__main__":
    sys.exit(main())
