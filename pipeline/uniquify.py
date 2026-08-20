"""
Уникализация: из одного мастера — несколько вариантов для разных аккаунтов.

Зачем. Один и тот же файл, залитый с семи аккаунтов, площадки видят как дубль
и режут охват, а при повторах — банят. Варианты должны отличаться так, чтобы
алгоритм считал их разными файлами, а зритель не заметил разницы.

    python uniquify.py master.mp4 --out-dir variants --count 4
    python uniquify.py master.mp4 --out-dir variants --count 3 --report var.json

Железное правило теста: **один вариант — одно отличие**, и оно записано.
Иначе это просто лишние публикации, из которых ничего не узнать.

Что меняется (по одному приёму на вариант):
    speed   скорость 0.97–1.03 — самый заметный для алгоритма, самый
            незаметный для глаза
    crop    обрезка 1–3 % с краёв
    color   температура и насыщенность на пару процентов
    audio   высота тона на четверть полутона
    pad     вставка одного кадра в начало — сдвигает всю хеш-дорожку

Чего скрипт не делает намеренно:
    зеркалить — в кадре текст, логотип и упаковка, зеркальные надписи видно
    сразу. Это первое, за что ролик считают ворованным.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"


def duration(path: str) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


# Скорость только вверх. Замедленный ролик проигрывает в ленте: он длиннее,
# а досмотр падает. Ускорение, наоборот, поднимает темп и досмотр.
#
# Звук при ускорении тянем через atempo — он держит высоту тона. Без него
# на 1.3× голос уезжает в мультяшный, и ролик выглядит переделкой.
#
# каждый приём: (ключ, человеческое описание, видеофильтр, аудиофильтр)
TRICKS: list[tuple[str, str, str, str]] = [
    ("speed-110", "скорость 1.10×", "setpts=PTS/1.10", "atempo=1.10"),
    ("speed-120", "скорость 1.20×", "setpts=PTS/1.20", "atempo=1.20"),
    ("speed-130", "скорость 1.30×", "setpts=PTS/1.30", "atempo=1.30"),
    ("speed-140", "скорость 1.40×", "setpts=PTS/1.40", "atempo=1.40"),
    ("crop-2", "обрезка 2 % по краям", "crop=iw*0.98:ih*0.98,scale=1080:1920", ""),
    ("color-warm", "теплее на 3 %", "eq=saturation=1.04:gamma_r=1.02:gamma_b=0.985", ""),
    ("crop-3", "обрезка 3 % снизу", "crop=iw:ih*0.97:0:0,scale=1080:1920", ""),
    ("color-cool", "холоднее на 3 %", "eq=saturation=0.97:gamma_b=1.02:gamma_r=0.985", ""),
    ("speed-105", "скорость 1.05×", "setpts=PTS/1.05", "atempo=1.05"),
]

# Ниже этой длительности ускорять опасно: ролик выпадет из минимума площадок
MIN_OK_SEC = 15.0


def make(src: str, dst: Path, vf: str, af: str) -> bool:
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src]
    if vf:
        cmd += ["-vf", vf]
    if af:
        cmd += ["-af", af]
    cmd += [
        "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1200:])
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="варианты одного ролика")
    ap.add_argument("src")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--count", type=int, default=4)
    ap.add_argument("--report", help="куда записать, что в каком варианте изменено")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"нет файла: {src}")
        return 1

    base_dur = duration(str(src))
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    n = min(args.count, len(TRICKS))
    if args.count > len(TRICKS):
        print(f"приёмов всего {len(TRICKS)}, делаю столько же")

    made: list[dict] = []
    print(f"{src.name}: {base_dur:.1f} с, делаю {n} вариант(ов)\n")

    for i in range(n):
        key, human, vf, af = TRICKS[i]
        dst = out / f"{src.stem}--{key}.mp4"
        if not make(str(src), dst, vf, af):
            print(f"  {key}: не собрался")
            continue
        d = duration(str(dst))
        made.append({
            "file": dst.name,
            "приём": key,
            "отличие": human,
            "сек": round(d, 2),
            "сдвиг длительности": round(d - base_dur, 2),
        })
        print(f"  {dst.name:<44} {human}  ({d:.1f} с)")

    # длительность — первое, на что смотрит алгоритм площадки при поиске дублей
    same = [m for m in made if abs(m["сдвиг длительности"]) < 0.05]
    if same:
        print(f"\n  внимание: у {len(same)} вариант(ов) длительность совпала с мастером —"
              f" для площадки это самый заметный признак дубля")

    # ускорение укорачивает ролик, а площадки режут охват коротким
    short = [m for m in made if m["сек"] < MIN_OK_SEC]
    if short:
        print(f"\n  ВНИМАНИЕ: {len(short)} вариант(ов) стали короче {MIN_OK_SEC:.0f} с "
              f"({', '.join(f'{m['сек']:.1f}' for m in short)}) — это ниже минимума площадок.")
        print(f"  Мастер должен быть длиннее: при ускорении 1.4× нужен исходник "
              f"от {MIN_OK_SEC * 1.4:.0f} с.")

    if args.report:
        Path(args.report).write_text(
            json.dumps({"мастер": src.name, "варианты": made}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\nотчёт: {args.report}")

    print("\nодин вариант — одно отличие. Записывай в таблицу, какой аккаунт получил какой,"
          "\nиначе по результатам будет непонятно, что сработало.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
