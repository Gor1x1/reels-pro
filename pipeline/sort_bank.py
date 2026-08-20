"""
Раскладка банка рилсов по папкам с понятными именами.

Файлы, выгруженные из Instagram, называются служебными хешами — по имени
не понять ничего. Скрипт копирует их в структуру товара под именами вида
`DYU-hook-cafe-stain-21.mp4` и разводит по папкам:

    clean/          без вшитого текста — годятся для пересборки, это главный ресурс
    subs/           со вшитыми субтитрами — публикация и уникализация как есть
    old-clean/      то же из старой партии
    other-product/  другой товар линейки, в ролики про гель не брать
    duplicates/     дубли `Copy of`
    unsorted/       ещё не просмотрено глазами

Оригиналы на рабочем столе не трогаются: копируем, а не переносим.

    python sort_bank.py
    python sort_bank.py --index      — только пересобрать index.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(os.path.expandvars(r"%USERPROFILE%\Desktop"))
SRC_IG = DESKTOP / "Videos-Dyurin" / "Reels instagram"
SRC_OLD = DESKTOP / "Videos-Dyurin" / "Videos"
BASE = Path(r"C:\Ferma\factory\products\гель-дюрин\stock-reels")

FFPROBE = shutil.which("ffprobe") or "ffprobe"

FOLDERS = ["clean", "subs", "old-clean", "other-product", "duplicates", "unsorted"]

# Позиция файла в списке (по алфавиту) → папка, имя, что в кадре.
# Категории проставлены после просмотра кадров каждого ролика.
IG_MAP: dict[int, tuple[str, str, str]] = {
    1:  ("clean", "sink-brush", "раковина, щётка, мыло, чистка сантехники"),
    2:  ("clean", "table-cloth", "стол, скатерть, деревянная доска, бутылка"),
    3:  ("subs", "stove-cabinets", "плита и кухонные шкафы, текст внизу"),
    4:  ("subs", "fabric-howto", "инструкция по ткани, текст по центру"),
    5:  ("clean", "fabric-bag", "белая ткань и сумка, стирка руками"),
    6:  ("subs", "blogger-facts", "блогер в кадре рассказывает, цифры на экране"),
    7:  ("subs", "compare-brands", "сравнение с другим средством, две бутылки"),
    8:  ("clean", "stove-gloves", "плита, жёлтые перчатки, кухня"),
    9:  ("subs", "tips-five", "пять применений, пронумерованный текст"),
    10: ("subs", "store-shelf", "магазин, полки с товаром, корзина"),
    11: ("subs", "jeans-oil", "джинсы, пятна масла, текст внизу"),
    12: ("clean", "floor-tile", "пол, плитка, мытьё"),
    13: ("subs", "hair-brush", "уход, расчёска, мелкий текст сверху"),
    14: ("clean", "stove-sponge", "кухня, плита, чистка губкой"),
    15: ("clean", "soak-basin", "замачивание белья в тазу, перчатки"),
    16: ("clean", "laundry-home", "стиральная машина, уборка дома"),
    17: ("clean", "fabric-bowl", "белая ткань, миска, бутылка"),
    18: ("clean", "bathroom-drain", "ванная, волосы, слив, раковина"),
    19: ("subs", "stroller", "детская коляска, текст на плашках"),
    20: ("clean", "product-sink", "бутылка на столе, раковина"),
    21: ("clean", "hook-cafe-stain", "ХУК: кафе, салат, пятно на футболке"),
    22: ("clean", "dishes", "посуда, губка, мойка"),
    23: ("subs", "laundry-tips", "стиральная машина, текст-совет"),
    24: ("clean", "sink-floor", "раковина, слив, пол, корзина с товаром"),
    25: ("clean", "hook-spill", "ХУК: пролитое на белой ткани, вытирают"),
    26: ("subs", "kitchenware", "сковорода, чайник, текст внизу"),
    27: ("clean", "car-seat", "салон машины, чистка сиденья"),
    28: ("clean", "hook-red-stain", "ХУК: красное пятно на белом, крупно"),
    29: ("subs", "chair-pen", "стул, след от ручки, текст"),
    30: ("clean", "stove-induction", "индукционная плита, чистка"),
    31: ("clean", "kitchen-cooking", "кухня, готовка, помидоры, плита"),
    32: ("clean", "hook-stains-two", "ХУК: два пятна — жёлтое и кетчуп"),
    33: ("clean", "shoes-white", "белые кроссовки, чистка губкой"),
    34: ("clean", "fabric-shirt", "пятно на ткани, голубая рубашка"),
}

# Старая партия: категория выводится из имени файла
OTHER_PRODUCT = re.compile(r"Սպեղանի|Speghani|Spghani|Ձեռքերի|Կրունկի|Parik", re.IGNORECASE)
COPY_PREFIX = re.compile(r"^Copy of ", re.IGNORECASE)
OLD_CLEAN = re.compile(r"Karmir hetq", re.IGNORECASE)


def probe(path: Path) -> dict:
    try:
        out = subprocess.run(
            [FFPROBE, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
        data = json.loads(out)
    except (json.JSONDecodeError, OSError):
        return {}
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "sec": round(float(data.get("format", {}).get("duration", 0) or 0), 1),
        "w": v.get("width"),
        "h": v.get("height"),
        "mb": round(int(data.get("format", {}).get("size", 0) or 0) / 1024 / 1024, 1),
    }


def safe_name(stem: str) -> str:
    s = re.sub(r"[^\w\-. ]", "", stem, flags=re.UNICODE)
    return re.sub(r"\s+", "-", s).strip("-") or "clip"


def main() -> int:
    ap = argparse.ArgumentParser(description="раскладка банка рилсов")
    ap.add_argument("--index", action="store_true", help="только пересобрать index.json")
    args = ap.parse_args()

    for f in FOLDERS:
        (BASE / f).mkdir(parents=True, exist_ok=True)

    index: list[dict] = []

    if not args.index:
        # новая партия из Instagram
        if SRC_IG.exists():
            files = sorted(
                [p for p in SRC_IG.rglob("*") if p.suffix.lower() in (".mp4", ".mov")],
                key=lambda p: p.name,
            )
            for n, src in enumerate(files, 1):
                if n not in IG_MAP:
                    continue
                folder, name, what = IG_MAP[n]
                dst = BASE / folder / f"DYU-{name}-{n:02d}.mp4"
                shutil.copy2(src, dst)

        # старая партия
        if SRC_OLD.exists():
            for src in SRC_OLD.rglob("*"):
                if src.suffix.lower() not in (".mp4", ".mov"):
                    continue
                stem = src.stem
                if COPY_PREFIX.search(stem):
                    folder = "duplicates"
                elif OTHER_PRODUCT.search(stem):
                    folder = "other-product"
                elif OLD_CLEAN.search(stem):
                    folder = "old-clean"
                else:
                    folder = "unsorted"
                shutil.copy2(src, BASE / folder / f"{safe_name(stem)}.mp4")

    # индекс по тому, что лежит в папках
    what_by_name = {f"DYU-{v[1]}-{k:02d}": v[2] for k, v in IG_MAP.items()}
    for folder in FOLDERS:
        for p in sorted((BASE / folder).glob("*.mp4")):
            info = probe(p)
            index.append({
                "file": f"{folder}/{p.name}",
                "folder": folder,
                "clean": folder in ("clean", "old-clean"),
                "what": what_by_name.get(p.stem, ""),
                **info,
            })

    (BASE / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n=== банк: {BASE} ===")
    for f in FOLDERS:
        c = len(list((BASE / f).glob("*.mp4")))
        if c:
            secs = sum(x.get("sec", 0) or 0 for x in index if x["folder"] == f)
            print(f"  {f:<15} {c:>3} шт   {secs / 60:>5.1f} мин")
    print(f"\n  индекс: {BASE / 'index.json'} ({len(index)} записей)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
