"""
Чтение и запись таблицы завода. Агенты дёргают этот модуль, а не Google API.

Смысл обёртки — в правилах, которые нельзя нарушать, и которые легко нарушить,
работая с API напрямую:

  · **в серые ячейки не писать.** Там формулы. Впишешь число — формула
    исчезнет навсегда, и колонка перестанет считаться для всех строк ниже.
    Это самая дорогая ошибка в таблице, поэтому модуль пишет только в колонки
    из белого списка.
  · **строки не удалять.** Нужно убрать запись — очистить значения.
    Удаление строки уносит формулы вместе с ней.
  · ID ТЗ обязан быть формата `M1-K1-ГЕЛ-001`: по нему публикации находят
    своё задание. Ошибся — ролик потерялся.

    python sheets.py check                      — проверить доступ
    python sheets.py read Продюсинг --limit 5
    python sheets.py add-tz --id M1-K1-ГЕЛ-001 --product "Гель Дюрин" \\
        --format "Обзор товара" --about "Разбираю состав" --creator "Ани"

Доступ: файл ключа сервис-аккаунта. Положить в `factory/config/google-key.json`
либо указать путь в переменной окружения `ZAVOD_GOOGLE_KEY`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEY_PATHS = [
    Path(os.environ.get("ZAVOD_GOOGLE_KEY", "")),
    Path(r"C:\Ferma\factory\config\google-key.json"),
    ROOT / "config" / "google-key.json",
]
SHEET_ID_FILE = Path(r"C:\Ferma\factory\config\sheet-id.txt")

# Колонки, в которые агенту можно писать. Всё остальное — формулы и замеры,
# их трогать нельзя. Буквы взяты из инструкции по таблице.
WRITABLE: dict[str, dict[str, str]] = {
    "Продюсинг": {
        "A": "Дата выдачи ТЗ", "B": "ID ТЗ", "C": "Товар / артикул",
        "D": "Формат", "E": "Короткое описание видео", "F": "Креатор",
        "H": "Дедлайн публикации",
    },
    "Публикации": {
        "A": "ID публикации", "B": "Дата", "C": "ID ТЗ", "D": "Креатор",
        "E": "Товар", "F": "Формат", "G": "Соцсеть", "H": "Аккаунт", "I": "Ссылка",
    },
    "Референсы": {
        "A": "Дата находки", "B": "Где нашёл", "C": "Ссылка",
        "D": "Просмотров у оригинала", "E": "Ниша", "F": "Хук первые 3 сек",
        "G": "Почему сработало", "H": "Разбор покадрово",
    },
}

TZ_ID = re.compile(r"^M\d+-[KF]\d+-[А-ЯЁA-Z]{2,4}-\d{3}$")


def find_key() -> Path | None:
    for p in KEY_PATHS:
        if p and p.name and p.exists():
            return p
    return None


def client():
    key = find_key()
    if not key:
        print("нет ключа доступа к таблице.")
        print("Положить файл сервис-аккаунта в C:\\Ferma\\factory\\config\\google-key.json")
        print("и дать этому аккаунту доступ к книге (кнопка «Поделиться» в таблице).")
        return None, None
    try:
        import gspread  # type: ignore
    except ImportError:
        print("нужен gspread: python -m pip install gspread google-auth")
        return None, None

    try:
        gc = gspread.service_account(filename=str(key))
    except Exception as e:  # ключ битый или не тот тип
        print(f"ключ не подошёл: {e}")
        return None, None

    if not SHEET_ID_FILE.exists():
        print(f"нет файла с адресом книги: {SHEET_ID_FILE}")
        print("Положить туда ID таблицы — это часть ссылки между /d/ и /edit.")
        return gc, None
    return gc, SHEET_ID_FILE.read_text(encoding="utf-8").strip()


def open_sheet(name: str):
    gc, sid = client()
    if not gc or not sid:
        return None
    try:
        return gc.open_by_key(sid).worksheet(name)
    except Exception as e:
        print(f"не открылся лист «{name}»: {e}")
        return None


def check() -> int:
    gc, sid = client()
    if not gc or not sid:
        return 1
    try:
        book = gc.open_by_key(sid)
    except Exception as e:
        print(f"книга не открылась: {e}")
        return 1
    print(f"\nкнига: {book.title}\nлисты:")
    for ws in book.worksheets():
        mark = " (пишем)" if ws.title in WRITABLE else ""
        print(f"  {ws.title}{mark}")
    print()
    return 0


def read(name: str, limit: int) -> int:
    ws = open_sheet(name)
    if not ws:
        return 1
    rows = ws.get_all_values()[:limit + 1]
    for r in rows:
        print(" | ".join(c[:22] for c in r[:9]))
    return 0


def add_tz(args) -> int:
    if not TZ_ID.match(args.id):
        print(f"ID «{args.id}» не по формату. Нужно вида M1-K1-ГЕЛ-001:")
        print("  модуль · креатор · три буквы товара · номер по порядку.")
        print("По этому ID публикации находят своё ТЗ — ошибка потеряет ролик.")
        return 1

    ws = open_sheet("Продюсинг")
    if not ws:
        return 1

    existing = ws.col_values(2)
    if args.id in existing:
        print(f"ID {args.id} уже есть в таблице, строка {existing.index(args.id) + 1}")
        return 1

    # пишем только в жёлтые колонки A–F, остальное считает таблица сама
    row = [args.date, args.id, args.product, args.format, args.about, args.creator]
    ws.append_row(row, value_input_option="USER_ENTERED", table_range="A1:F1")
    print(f"добавлено ТЗ {args.id}")
    print("серые колонки не трогал — дедлайны и статусы посчитаются сами")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="таблица завода")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check")

    r = sub.add_parser("read")
    r.add_argument("sheet")
    r.add_argument("--limit", type=int, default=5)

    t = sub.add_parser("add-tz")
    t.add_argument("--id", required=True)
    t.add_argument("--product", required=True)
    t.add_argument("--format", required=True)
    t.add_argument("--about", required=True)
    t.add_argument("--creator", required=True)
    t.add_argument("--date", default="")

    args = ap.parse_args()

    if args.cmd == "check":
        return check()
    if args.cmd == "read":
        return read(args.sheet, args.limit)
    if args.cmd == "add-tz":
        if not args.date:
            from datetime import date
            args.date = date.today().strftime("%d.%m.%Y")
        return add_tz(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
