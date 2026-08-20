"""
Образцы голоса для клонирования — из своих же роликов.

Сервисы клонирования просят 1–3 минуты чистой речи одного человека. В банке
такая речь уже есть: говорящие головы сняты без музыки и без закадрового шума.
Скрипт достаёт звук, чистит его и склеивает в один файл, пригодный для загрузки.

    python voicebank.py --list                       — кто есть в банке
    python voicebank.py --voice talk-4k --out voices/CP-01.wav

Что делает со звуком: убирает постоянный шум комнаты, срезает низ ниже 80 Гц,
выравнивает громкость. Компрессию и эквалайзер НЕ применяет намеренно —
клонированию нужен голос как он есть, обработанный звук даёт неестественный клон.

**Клонировать голос можно только с письменного согласия человека.**
Это относится и к своим креаторам тоже: право на ролик и право на голос —
разные вещи, и второе должно быть в договоре отдельной строкой.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BANK = Path(r"C:\Ferma\factory\products\гель-дюрин\stock-reels")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# Кто говорит в каких роликах. Собрано просмотром банка.
VOICES: dict[str, tuple[str, list[str]]] = {
    "talk-4k": (
        "девушка в розовой рубашке, 4K-серия, армянский — самая чистая речь в банке",
        [
            "clean/DYU-4k-talk-stains.mp4",
            "clean/DYU-4k-talk-effect.mp4",
            "clean/DYU-4k-talk-color.mp4",
            "clean/DYU-4k-talk-safety.mp4",
            "clean/DYU-4k-talk-purpose.mp4",
        ],
    ),
    "blonde": (
        "блондинка на кухне, армянский — есть вшитый текст, но звук чистый",
        ["subs/DYU-numbers-sold.mp4", "subs/DYU-talk-mission.mp4", "subs/DYU-blogger-facts-06.mp4"],
    ),
    "seda": (
        "рыжая девушка, армянский",
        ["subs/DYU-seda-stains.mp4", "subs/DYU-seda-pan.mp4", "subs/DYU-seda-dishes.mp4"],
    ),
    # Найдены замером высоты голоса: 172 Гц против 211–225 у 4K-серии.
    # Разница больше 35 Гц — это точно другой человек.
    "low": (
        "низкий женский голос, ~172 Гц — заметно ниже остальных в банке",
        [
            "clean/DYU-laundry-home-16.mp4",
            "clean/DYU-soak-basin-15.mp4",
            "clean/DYU-fabric-bowl-17.mp4",
            "clean/DYU-floor-tile-12.mp4",
            "subs/DYU-uniq-Դյուրին-տուն-մաքրել.mp4",
            "subs/DYU-uniq-Բոթասի-վիդեո.mp4",
        ],
    ),
    "high": (
        "высокий голос, ~258 Гц",
        ["clean/DYU-fabric-shirt-34.mp4"],
    ),
    "highest": (
        "самый высокий в банке, ~314 Гц",
        ["clean/DYU-stove-sponge-14.mp4"],
    ),

    # Партия, присланная отдельно под голоса. Группы найдены замером высоты
    # и совпали с тем, как владелец их и присылал: три ролика одним голосом,
    # два другим, остальные поодиночке.
    "new-a": (
        "~234 Гц, три ролика одним голосом",
        ["voice-in/v01.mp4", "voice-in/v02.mp4", "voice-in/v03.mp4"],
    ),
    "new-b": (
        "~281 Гц, самый высокий из партии, два ролика",
        ["voice-in/v06.mp4", "voice-in/v08.mp4"],
    ),
    "new-c": ("~225 Гц", ["voice-in/v07.mp4"]),
    "new-d": ("~254 Гц", ["voice-in/v04.mp4"]),
    "new-e": ("~267 Гц", ["voice-in/v05.mp4"]),
}


def duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description="образцы голоса для клонирования")
    ap.add_argument("--voice", help="ключ голоса из списка")
    ap.add_argument("--out", help="куда сохранить образец (.wav)")
    ap.add_argument("--list", action="store_true", help="показать, кто есть в банке")
    args = ap.parse_args()

    if args.list or not args.voice:
        print("\nголоса в банке:\n")
        for key, (what, files) in VOICES.items():
            total = sum(duration(BANK / f) for f in files if (BANK / f).exists())
            mark = "хватит" if total >= 60 else "маловато"
            print(f"  {key:<10} {total / 60:.1f} мин  ({mark})  {what}")
        print("\nдля клонирования просят 1–3 минуты. Меньше минуты — клон выйдет плоским.\n")
        return 0

    if args.voice not in VOICES:
        print(f"нет такого голоса: {args.voice}")
        return 1
    if not args.out:
        print("нужен --out")
        return 1

    _, files = VOICES[args.voice]
    exist = [BANK / f for f in files if (BANK / f).exists()]
    if not exist:
        print("файлы голоса не найдены в банке")
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, src in enumerate(exist):
            wav = Path(tmp) / f"p{i}.wav"
            # моно 44.1 кГц — то, что просят почти все сервисы клонирования
            r = subprocess.run(
                [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                 "-vn", "-af", "highpass=f=80,afftdn=nf=-28,loudnorm=I=-18:TP=-2",
                 "-ac", "1", "-ar", "44100", str(wav)],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                parts.append(wav)
                print(f"  взял {src.name}  ({duration(src):.1f} с)")

        if not parts:
            print("не удалось извлечь звук")
            return 1

        lst = Path(tmp) / "list.txt"
        lst.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", str(lst),
             "-ac", "1", "-ar", "44100", str(out)],
            capture_output=True,
        )

    total = duration(out)
    print(f"\nобразец: {out}  ({total / 60:.1f} мин)")
    if total < 60:
        print("  короче минуты — клон получится плоским, добавь записей")
    print("\nЗагружать в сервис клонирования только при письменном согласии человека.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
