"""
Разбор папки unsorted после просмотра кадров глазами.

Каждый ролик отнесён к clean или subs и описан: что в кадре, что из него
можно брать и с чем клеить. Описания идут в bank.md — каталог, по которому
собираются ролики, не пересматривая исходники заново.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BASE = Path(r"C:\Ferma\factory\products\гель-дюрин\stock-reels")

# имя файла → (папка, новое имя, что в кадре)
DECIDED: dict[str, tuple[str, str, str]] = {
    # --- чистые, без вшитого текста ---
    "ARPI-1": ("clean", "DYU-4k-cooking-stove", "4K. Готовка на кухне, нарезка, сковорода, затем грязная плита и чистка губкой"),
    "ARPI-2": ("clean", "DYU-4k-hook-cafe-stain", "4K. ХУК: кафе, салат, пятно на белой футболке, нанесение, стирка"),
    "Anvtang": ("clean", "DYU-4k-talk-safety", "4K. Говорящая голова, розовая рубашка, кухня. Тема безопасности состава"),
    "Efektivutyun": ("clean", "DYU-4k-talk-effect", "4K. Говорящая голова, та же съёмка. Тема эффективности"),
    "Gunavor": ("clean", "DYU-4k-talk-color", "4K. Говорящая голова. Тема цветного белья"),
    "Hetqer": ("clean", "DYU-4k-talk-stains", "4K. Говорящая голова + вставка с двумя бутылками. Тема следов и пятен"),
    "Npatak": ("clean", "DYU-4k-talk-purpose", "4K. Говорящая голова. Тема назначения средства"),
    "IMG_7028": ("clean", "DYU-mood-home-light", "Атмосфера дома: скатерть, солнечный свет, корзина, ткань. Проходные кадры"),
    "Kitchen": ("clean", "DYU-induction-foam", "Индукционная плита, нанесение, густая пена, чистка до блеска"),
    "Lilia": ("clean", "DYU-wall-sponge", "Стена и поверхность, нанесение, чистка красной губкой"),
    "lvacaran": ("clean", "DYU-sink-gloves", "Раковина, жёлтые перчатки, губка, вода из крана"),
    "Lvacaran-asmr": ("clean", "DYU-sink-asmr", "ASMR: раковина, щётка, вода, крупные планы без речи"),
    "Marina": ("clean", "DYU-dishes-blue-gloves", "Мытьё посуды, синие перчатки, губка, пена"),
    "Xohanoc": ("clean", "DYU-kitchen-full", "Кухня целиком: перчатки, пена, раковина, швабра, уборка"),
    "Polina": ("clean-lowres", "DYU-lowres-sink", "Раковина и слив. Разрешение 480x854 — только как вставка, не на весь кадр"),

    # --- со вшитым текстом ---
    "Dyurin-araqelutyun": ("subs", "DYU-talk-mission", "Блондинка с бутылкой, текст внизу. Тема миссии бренда"),
    "Dyurin-asmr": ("subs", "DYU-swap-bottles-1", "СИЛЬНЫЙ КАДР: стол с чужими средствами, рука убирает их, остаётся одна бутылка"),
    "Dyurin-asmr-2": ("subs", "DYU-swap-bottles-2", "То же, другой ракурс: замена шкафа химии одной бутылкой"),
    "Dyurin-koshik-2": ("subs", "DYU-shoes-machine", "Грязные кроссовки, чистка, стиральная машина"),
    "Dyurin-koshikner-1": ("subs", "DYU-shoes-basin", "Белая обувь, замачивание в тазу, чистка губкой"),
    "Dyurin-maqrutyun": ("subs", "DYU-kitchen-swap", "Блондинка с чужими средствами, затем уборка кухни"),
    "Dyurin-գազօջախ": ("subs", "DYU-gas-stove", "Газовая плита: грязная, нанесение, чистка. Текст на 68% высоты"),
    "Dyurin-տան-մաքրելու-վիդ.-վոյսովեր": ("subs", "DYU-home-voiceover", "Уборка дома под закадровый голос, щётка, перчатки"),
    "Hamematutyun": ("subs", "DYU-compare-short", "Короткое сравнение: чужие бутылки убирают, остаётся Dyurin"),
    "mrtzlva": ("subs", "DYU-ru-oven", "РУССКАЯ этикетка и русский текст. Духовка, противень, чистка"),
    "Nadezhda": ("subs", "DYU-ru-bathroom", "РУССКАЯ этикетка и русский текст. Ванная, стакан, полотенце"),
    "SEDA-1": ("subs", "DYU-seda-stains", "Рыжая девушка, бутылка, футболка с пятнами кофе и соуса"),
    "SEDA-2": ("subs", "DYU-seda-pan", "Рыжая девушка, сильно пригоревшая сковорода, чистка"),
    "SEDA-3": ("subs", "DYU-seda-dishes", "Рыжая девушка, гора грязной посуды в раковине"),
    "SEDA-4": ("subs", "DYU-seda-shoes", "Рыжая девушка, грязные кроссовки, чистка щёткой"),
    "SEDA-5": ("subs", "DYU-seda-window", "Бутылка и мытьё окна тряпкой"),
    "Դյուրին-գոհ-հաճախորդ": ("subs", "DYU-numbers-sold", "Блондинка, цифры продаж на экране: 74.482 шт, 54.126 покупателей"),
    "Լաքա-1": ("subs", "DYU-stain-full-subs", "Полный сюжет с соусом на футболке. То же, что чистый Karmir hetq, но с текстом"),
    "Լաքա-2": ("subs", "DYU-stain-short-subs", "Короткий сюжет: ткань, нанесение, смывание"),
    "Համեմատություն": ("subs", "DYU-compare-two", "Сравнение двух средств, руки на футболке, соус, стирка"),
}


def main() -> int:
    src = BASE / "unsorted"
    (BASE / "clean-lowres").mkdir(parents=True, exist_ok=True)

    moved = 0
    for p in sorted(src.glob("*.mp4")):
        rec = DECIDED.get(p.stem)
        if not rec:
            print(f"  не размечен, оставляю в unsorted: {p.name}")
            continue
        folder, name, _ = rec
        dst = BASE / folder / f"{name}.mp4"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dst))
        moved += 1

    print(f"\nразложено: {moved}")
    for f in ("clean", "clean-lowres", "subs", "old-clean", "unsorted"):
        d = BASE / f
        if d.exists():
            c = len(list(d.glob("*.mp4")))
            if c:
                print(f"  {f:<14} {c:>3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
