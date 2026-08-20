"""
Подготовка исходников к монтажу и мастеринг готового ролика.

Куски из разных источников стыкуются только если приведены к одному
знаменателю: 1080×1920, 30 fps, h264 + aac. Иначе на склейке видно смену
кодека — картинка дёргается, а Remotion на части файлов просто спотыкается.

    python prep.py shots  <файлы...> --out public/src   — привести к общему формату
    python prep.py voice  <файл> --out voice.wav        — чистка и мастеринг речи
    python prep.py master <файл> --out final.mp4        — громкость финала −14 LUFS

Кадрирование горизонтали задаётся ключом --fit:
    crop  — обрезать по центру, кадр остаётся честным (по умолчанию)
    blur  — вписать на размытый фон; выглядит дешевле, но сохраняет весь кадр
    pad   — вписать на чёрное поле
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

W, H = 1080, 1920
FPS = 30


def run(cmd: list[str]) -> int:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        sys.stderr.write((p.stderr or "")[-2000:])
    return p.returncode


def vfilter(fit: str, shift: float) -> str:
    """
    shift — сдвиг окна кадрирования по горизонтали, −1..1. Нужен, когда
    интересное происходит не по центру: товар в руках справа, лицо слева.
    """
    if fit == "blur":
        return (
            f"split[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=42:6[bg];"
            f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,fps={FPS}"
        )
    if fit == "pad":
        return (
            f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,fps={FPS}"
        )
    # crop: увеличиваем до перекрытия и вырезаем окно с нужным сдвигом
    x = f"(iw-{W})/2+({shift})*(iw-{W})/2"
    return f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:{x}:(ih-{H})/2,fps={FPS}"


def prep_shot(src: str, out_dir: Path, fit: str, shift: float, denoise: bool) -> str | None:
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{Path(src).stem}.mp4"

    af = "aresample=48000"
    if denoise:
        # мягкая чистка: убирает шум комнаты, речь не трогает
        af = "afftdn=nf=-25,highpass=f=80," + af

    cmd = [
        FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-vf", vfilter(fit, shift),
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-af", af,
        # звук всегда aac: Remotion не читает mp4 с mp3 внутри
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(dst),
    ]
    if run(cmd) != 0:
        print(f"  не удалось подготовить: {src}")
        return None
    print(f"  {Path(src).name} -> {dst.name}")
    return str(dst)


def prep_voice(src: str, dst: str) -> int:
    """
    Мастеринг речи: фильтр низов, компрессия, подъём разборчивости на 3 кГц,
    громкость под площадки. Порядок фильтров важен — сначала чистим, потом жмём.
    """
    return run(
        [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
            "-af",
            "highpass=f=80,afftdn=nf=-25,"
            "acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
            "equalizer=f=3000:width_type=q:w=1.2:g=2,"
            "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le", "-ar", "48000", dst,
        ]
    )


def master(src: str, dst: str) -> int:
    """
    Финальная громкость. −14 LUFS — то, к чему приводят все семь площадок.

    Обязательно в два прохода. Однопроходный loudnorm работает адаптивно и
    промахивается мимо цели на 2–3 LUFS: на проверке это выглядит как брак,
    хотя фильтр отработал. Сначала измеряем, потом применяем с измеренными
    значениями — тогда попадание точное.

    Мерить нужно ровно ту цепочку, что пойдёт в дело, вместе с компрессором.
    Замер по чистому исходнику даёт loudnorm неверную точку отсчёта: он
    считает вход громче, чем тот есть после компрессии, и уводит громкость
    вниз. На ролике с озвучкой это давало −17.4 LUFS вместо −14 при том, что
    до мастеринга было −13.
    """
    # Лёгкая компрессия перед нормализацией. Со звуком исходников (вода,
    # шорох, голос) пик-фактор высокий, и loudnorm упирается в потолок
    # по пикам раньше, чем догоняет цель по средней громкости.
    pre = "acompressor=threshold=-14dB:ratio=2.5:attack=6:release=140"

    probe = subprocess.run(
        [FFMPEG, "-hide_banner", "-nostats", "-i", src,
         "-af", f"{pre},loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
         "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (probe.stderr or "") + (probe.stdout or "")

    af = f"{pre},loudnorm=I=-14:TP=-1.5:LRA=11"
    m = re.search(r"\{[^{}]*input_i[^{}]*\}", out, re.DOTALL)
    if m:
        try:
            d = json.loads(m.group(0))
            af = (
                f"{pre},loudnorm=I=-14:TP=-1.5:LRA=11"
                f":measured_I={d['input_i']}:measured_TP={d['input_tp']}"
                f":measured_LRA={d['input_lra']}:measured_thresh={d['input_thresh']}"
                f":offset={d['target_offset']}"
            )
        except (json.JSONDecodeError, KeyError):
            pass
    else:
        sys.stderr.write("не удалось измерить громкость, иду одним проходом\n")

    return run(
        [
            FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
            "-c:v", "copy",
            "-af", af,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", dst,
        ]
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="подготовка исходников и мастеринг")
    ap.add_argument("cmd", choices=["shots", "voice", "master"])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True, help="папка для shots, файл для voice и master")
    ap.add_argument("--fit", choices=["crop", "blur", "pad"], default="crop")
    ap.add_argument("--shift", type=float, default=0.0, help="сдвиг кадра −1..1")
    ap.add_argument("--denoise", action="store_true", help="чистить шум комнаты")
    args = ap.parse_args()

    if args.cmd == "shots":
        print(f"привожу {len(args.paths)} файл(ов) к {W}x{H} {FPS}fps:")
        done = [prep_shot(p, Path(args.out), args.fit, args.shift, args.denoise) for p in args.paths]
        ok = [d for d in done if d]
        print(f"готово: {len(ok)} из {len(args.paths)}")
        return 0 if len(ok) == len(args.paths) else 1

    if args.cmd == "voice":
        return prep_voice(args.paths[0], args.out)

    return master(args.paths[0], args.out)


if __name__ == "__main__":
    sys.exit(main())
