# -*- coding: utf-8 -*-
r"""Индекс банков и отчёт по накопленному.

    python bank_report.py index  <папка banks>   → ИНДЕКС.md
    python bank_report.py report <папка banks>   → ОТЧЁТ-БАНКОВ.md

**index** — служебный файл для агента. Банки растут: у одного товара
уже под две тысячи строк, и читать их целиком перед каждой задачей
дорого и бессмысленно. Индекс собирает из всех семи банков одну таблицу
на 100–200 строк: номер, название, статус, счётчики, под какую боль.
Агент читает индекс, находит нужные номера и открывает точечно только
их — по методу «сначала каталог, потом страница».

**report** — отчёт человеку раз в месяц. Что в банках накопилось: какие
механики живучи (счётчик «у чужих» растёт), что мы уже много раз снимали,
что ни разу не брали, какие боли возвращаются, где банк недособран.

Оба режима работают только на локальных файлах, ничего не стоят.
"""
import io
import os
import re
import sys
from collections import Counter

BANKS = [
    ("hooks.md",       "H", "хуки"),
    ("development.md", "R", "развития"),
    ("endings.md",     "C", "концовки"),
    ("techniques.md",  "T", "приёмы"),
    ("fails.md",       "F", "провалы"),
    ("pains.md",       "P", "боли"),
    ("combos.md",      "X", "связки"),
]

# «**Статус:** новый · у чужих 2 · у нас 0» — счётчики живут в этой строке
RE_STATUS = re.compile(r"\*\*Статус[:.]?\*\*\s*([^\n·]+)", re.I)
RE_THEIRS = re.compile(r"у чужих\s*(\d+)", re.I)
RE_OURS = re.compile(r"у нас\s*(\d+)", re.I)
RE_PAIN = re.compile(r"\*\*Под боль[:.]?\*\*\s*([^\n]+)", re.I)
RE_MET = re.compile(r"\*\*встречалось[:.]?\*\*\s*(\d+)", re.I)
RE_PRIORITY = re.compile(r"\*\*Приоритет[:.]?\*\*\s*(\d+)", re.I)
RE_FORMAT = re.compile(r"\*\*Формат[:.]?\*\*\s*([^\n·]+)")
RE_TYPE = re.compile(r"\*\*Тип[:.]?\*\*\s*([^\n·]+)")


def say(s):
    try:
        print(s)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((s + "\n").encode("utf-8"))


def parse_bank(path, letter):
    """Каждая запись банка — от '## X-NNN' до следующей такой строки."""
    if not os.path.exists(path):
        return []
    text = io.open(path, encoding="utf-8").read()
    heads = list(re.finditer(r"^##\s+(" + letter + r"-\d+)\s*·?\s*(.*)$", text, re.M))
    out = []
    for i, m in enumerate(heads):
        body = text[m.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        rec = {"номер": m.group(1), "название": m.group(2).strip().strip("«»"), "тело": body}
        s = RE_STATUS.search(body)
        rec["статус"] = s.group(1).strip() if s else "—"
        for key, rx in (("у_чужих", RE_THEIRS), ("у_нас", RE_OURS),
                        ("встречалось", RE_MET), ("приоритет", RE_PRIORITY)):
            mm = rx.search(body)
            rec[key] = int(mm.group(1)) if mm else None
        for key, rx in (("боль", RE_PAIN), ("формат", RE_FORMAT), ("тип", RE_TYPE)):
            mm = rx.search(body)
            rec[key] = mm.group(1).strip().rstrip(".") if mm else ""
        out.append(rec)
    return out


def read_all(folder):
    data = {}
    for fname, letter, human in BANKS:
        data[human] = parse_bank(os.path.join(folder, fname), letter)
    return data


def short(s, n=54):
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def build_index(folder, data):
    product = os.path.basename(os.path.dirname(os.path.abspath(folder)))
    total = sum(len(v) for v in data.values())
    L = ["# Индекс банков · %s" % product, "",
         "Служебный каталог для агента: **читается вместо самих банков**.",
         "Нашёл нужные номера здесь — открывай точечно только их, а не файл",
         "целиком. Банки растут, и сплошное чтение съедает работу впустую.",
         "",
         "Собирается заново после каждого прогона:",
         "`python lib/bank_report.py index products/<товар>/banks`",
         "", "Всего записей: **%d**" % total, "", "---", ""]
    for fname, letter, human in BANKS:
        rows = data.get(human) or []
        L.append("## %s · %s (%d)" % (letter, human, len(rows)))
        L.append("")
        if not rows:
            L.append("Пусто.")
            L.append("")
            continue
        if human == "боли":
            L.append("| № | Боль | Приоритет | Встречалось | Статус |")
            L.append("|---|---|---|---|---|")
            for r in rows:
                L.append("| %s | %s | %s | %s | %s |" % (
                    r["номер"], short(r["название"]), r["приоритет"] or "—",
                    r["встречалось"] or "—", r["статус"]))
        elif human == "хуки":
            L.append("| № | Хук | Тип | Под боль | У чужих | У нас | Статус |")
            L.append("|---|---|---|---|---|---|---|")
            for r in rows:
                L.append("| %s | %s | %s | %s | %s | %s | %s |" % (
                    r["номер"], short(r["название"], 44), short(r["тип"], 16),
                    short(r["боль"], 26), r["у_чужих"] or 0, r["у_нас"] or 0, r["статус"]))
        else:
            L.append("| № | О чём | У нас | Статус |")
            L.append("|---|---|---|---|")
            for r in rows:
                L.append("| %s | %s | %s | %s |" % (
                    r["номер"], short(r["название"]), r["у_нас"] or 0, r["статус"]))
        L.append("")
    L += ["---", "",
          "**Как пользоваться.** Нужен хук под боль «липнет к рукам» —",
          "найди строку в таблице `H`, возьми номер, открой в `hooks.md`",
          "только этот раздел. Нужно проверить, не повторяемся ли —",
          "смотри счётчик «у нас» здесь же, не открывая файл."]
    return "\n".join(L)


def build_report(folder, data):
    product = os.path.basename(os.path.dirname(os.path.abspath(folder)))
    hooks = data.get("хуки") or []
    pains = data.get("боли") or []
    devs = data.get("развития") or []
    L = ["# Отчёт по банкам · %s" % product, "",
         "Что накопилось и о чём это говорит. Считается по файлам банков,",
         "ничего не стоит. Полезно смотреть раз в месяц.", "", "---", ""]

    L += ["## Сколько чего", "", "| Банк | Записей |", "|---|---|"]
    for _, letter, human in BANKS:
        L.append("| %s · %s | %d |" % (letter, human, len(data.get(human) or [])))
    L.append("")

    # живучесть механик
    lively = sorted([h for h in hooks if (h["у_чужих"] or 0) >= 2],
                    key=lambda h: -(h["у_чужих"] or 0))
    L += ["## Механики, которые держатся", ""]
    if lively:
        L.append("Хук встретился у разных авторов больше одного раза — это уже")
        L.append("не случайность, а рабочая механика ниши.")
        L.append("")
        L.append("| № | Хук | Встретился раз |")
        L.append("|---|---|---|")
        for h in lively[:12]:
            L.append("| %s | %s | **%d** |" % (h["номер"], short(h["название"]), h["у_чужих"]))
    else:
        L.append("Пока ни один хук не встретился дважды: либо прогонов было мало,")
        L.append("либо ниша разнообразная. Вывод делать рано.")
    L.append("")

    # износ
    used = sorted([h for h in hooks if (h["у_нас"] or 0) > 0], key=lambda h: -(h["у_нас"] or 0))
    unused = [h for h in hooks if not (h["у_нас"] or 0)]
    L += ["## Что мы уже снимали, а что лежит нетронутым", ""]
    if used:
        L.append("| № | Хук | Наших роликов |")
        L.append("|---|---|---|")
        for h in used[:10]:
            L.append("| %s | %s | %d |" % (h["номер"], short(h["название"]), h["у_нас"]))
        L.append("")
        L.append("**Перебор одного хука изнашивает его.** Больше трёх роликов")
        L.append("подряд по одной механике — ставьте `отдых`.")
    else:
        L.append("**Ни один хук ещё не снят.** Счётчик «у нас» везде нулевой:")
        L.append("значит, банк пока хранит чужой опыт и не проверен на нашей")
        L.append("аудитории. Пока не будет замеров, все статусы — гипотезы.")
    L.append("")
    L.append("Нетронутых хуков: **%d из %d**." % (len(unused), len(hooks)))
    L.append("")

    # боли
    L += ["## Боли: что возвращается", ""]
    if pains:
        top = sorted(pains, key=lambda p: -(p["приоритет"] or 0))[:8]
        L.append("| № | Боль | Приоритет | Встречалось |")
        L.append("|---|---|---|---|")
        for p in top:
            L.append("| %s | %s | **%s** | %s |" % (
                p["номер"], short(p["название"]), p["приоритет"] or "—", p["встречалось"] or "—"))
        L.append("")
        repeat = [p for p in pains if (p["встречалось"] or 0) >= 5]
        if repeat:
            L.append("Подтверждены пятью и более независимыми цитатами: **%s**."
                     % ", ".join(p["номер"] for p in repeat[:10]))
            L.append("Такая боль живая, по ней стоит снимать регулярно.")
    else:
        L.append("Банк болей пуст.")
    L.append("")

    # типы хуков
    types = Counter(h["тип"] for h in hooks if h["тип"])
    if types:
        L += ["## Чем цепляет ниша", "", "| Тип хука | Записей |", "|---|---|"]
        for t, n in types.most_common(8):
            L.append("| %s | %d |" % (t, n))
        L.append("")
        L.append("Однобокий банк — риск: все ролики начнут звучать одинаково.")
        L.append("Стоит добирать типы, которых мало.")
        L.append("")

    # дыры
    L += ["## Где банк недособран", ""]
    holes = []
    if len(devs) < 20:
        holes.append("развитий %d при норме 20 — сценаристу не хватит уже к третьему дню" % len(devs))
    if len(data.get("провалы") or []) < 5:
        holes.append("провалов мало: не видно, что в нише не работает")
    if not (data.get("связки") or []):
        holes.append("связок нет — они появятся только после замеров наших публикаций")
    no_pain = [h for h in hooks if not h["боль"]]
    if no_pain:
        holes.append("хуков без привязки к боли: %d — их трудно применить" % len(no_pain))
    if holes:
        for h in holes:
            L.append("- " + h)
    else:
        L.append("Дыр не видно: все банки заполнены по норме.")
    L.append("")
    L += ["---", "",
          "**Главное ограничение.** Пока счётчик «у нас» нулевой, отчёт говорит",
          "о чужой нише, а не о вашей аудитории. Появятся замеры — те же",
          "таблицы начнут отвечать на вопрос «что работает у нас»."]
    return "\n".join(L)


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("index", "report"):
        sys.exit(__doc__)
    mode, folder = sys.argv[1], sys.argv[2]
    if not os.path.isdir(folder):
        sys.exit("нет папки банков: " + folder)
    data = read_all(folder)
    if mode == "index":
        out = os.path.join(folder, "ИНДЕКС.md")
        text = build_index(folder, data)
    else:
        out = os.path.join(folder, "ОТЧЁТ-БАНКОВ.md")
        text = build_report(folder, data)
    io.open(out, "w", encoding="utf-8").write(text)
    total = sum(len(v) for v in data.values())
    say("записей в банках: %d · записано: %s" % (total, out))


if __name__ == "__main__":
    main()
