"""
Папки товара. Один товар — одна папка, внутри девять креаторов, у каждого
своё сырьё и свои готовые ролики. Раскладка одинаковая всегда, поэтому найти
конкретный ролик можно не спрашивая.

    python product.py new гель-дюрин
    python product.py new гель-дюрин --title "Гель для стирки Дюрин" --sku 123456789
    python product.py list

Имя ролика собирается из кода: M1-K1-ГЕЛ-001. По нему видно модуль, креатора,
товар и номер — то же, что в таблице производства.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(r"C:\Ferma\factory\products")

# семь личностей фермы и двое живых
CREATORS = [f"CP-0{i}" for i in range(1, 8)] + ["c1", "c2"]

README = """# {title}

Артикул: {sku}

## Что где лежит

```
refs/                 фото товара со всех сторон — идут в промпты кадров
music/                треки под этот товар, сгенерированы pipeline/music.py
stock-reels/raw/      готовые чужие рилсы товара — материал для режима 3
stock-reels/index.json  разбор банка: что в каком файле по секундам
creators/<кто>/
    raw/              сырьё: что снял креатор или что сгенерировали
    ready/            смонтированные мастера, прошедшие проверку
    published/        то, что уже ушло в сети
runs/<дата>/<ID>/     рабочая папка одного ролика: spec, captions, кадры, лог
```

## Правила

- Мастер лежит в `ready/` под именем-кодом: `M1-K1-{code}-001.mp4`.
- После публикации файл переезжает в `published/`, а не копируется.
- Сырьё и кадры чистятся через семь дней после публикации, мастера остаются.
- Ничего не класть в корень папки товара — только в подпапки.

## Карточка

Заполнить `card.md` до первого ролика: что за товар, что решает, чего
обещать нельзя. Без карточки сценарист выдумает свойства, которых нет.
"""

CARD = """# {title}

- **Артикул WB:** {sku}
- **Ниша:**
- **Цена:**
- **Куда ведём трафик:**

## Что решает

## Главное отличие от аналогов

## Что нельзя обещать

Сюда — запрещённые формулировки: медицинские обещания, «на 100 %»,
сравнения с конкретными марками. Проверяющий сверяется с этим списком.

## Цифры, которые можно называть

Только измеримое и подтверждённое. Каждая цифра — с источником.
"""


def new(name: str, title: str | None, sku: str) -> int:
    base = ROOT / name
    if base.exists():
        print(f"папка уже есть: {base}")
        return 1

    code = name[:3].upper()
    title = title or name

    for sub in ("refs", "music", "stock-reels/raw", "runs"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    for c in CREATORS:
        for sub in ("raw", "ready", "published"):
            (base / "creators" / c / sub).mkdir(parents=True, exist_ok=True)

    (base / "README.md").write_text(
        README.format(title=title, sku=sku, code=code), encoding="utf-8"
    )
    (base / "card.md").write_text(CARD.format(title=title, sku=sku), encoding="utf-8")
    (base / "stock-reels" / "index.json").write_text("[]", encoding="utf-8")

    print(f"создано: {base}")
    print(f"  креаторов: {len(CREATORS)} ({', '.join(CREATORS)})")
    print(f"  заполни card.md и положи фото товара в refs/")
    return 0


def show() -> int:
    if not ROOT.exists():
        print(f"папки товаров ещё нет: {ROOT}")
        return 0
    items = sorted(p for p in ROOT.iterdir() if p.is_dir())
    if not items:
        print("товаров пока нет")
        return 0
    print(f"товары в {ROOT}:\n")
    for p in items:
        ready = len(list((p / "creators").rglob("ready/*.mp4")))
        pub = len(list((p / "creators").rglob("published/*.mp4")))
        stock = len(list((p / "stock-reels" / "raw").glob("*.mp4")))
        print(f"  {p.name:<24} готовых {ready:<4} опубликовано {pub:<4} банк рилсов {stock}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="папки товара")
    ap.add_argument("cmd", choices=["new", "list"])
    ap.add_argument("name", nargs="?")
    ap.add_argument("--title")
    ap.add_argument("--sku", default="—")
    args = ap.parse_args()

    if args.cmd == "list":
        return show()
    if not args.name:
        print("нужно имя товара")
        return 1
    return new(args.name, args.title, args.sku)


if __name__ == "__main__":
    sys.exit(main())
