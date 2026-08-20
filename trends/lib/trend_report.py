# -*- coding: utf-8 -*-
r"""Сводка по улову трендов: считает статистику из выгрузки Virlo.

    python trend_report.py <файл-выгрузки.txt|json> [--json путь]

На вход — ответ get_niche_monitor_data (data_type=videos), сохранённый
в файл. На выходе — распределение форматов и типов хука по победителям
против остальных, дословные хуки лидеров, сила залёта.

Сила залёта = ln(просмотры/подписчики) * ln(подписчики) — канон индустрии
(и Virlo). Победителями считаем верхнюю четверть по этой мере: сравнение
их распределения с нижней четвертью и есть playbook ниши.
"""
import json
import math
import re
import sys
from collections import Counter


def load(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    start = raw.find("{")
    if start > 0:
        raw = raw[start:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # выгрузка могла склеиться из нескольких кусков — берём первый объект
        depth, end = 0, None
        for i, ch in enumerate(raw):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        return json.loads(raw[:end])


def videos_of(doc):
    node = doc.get("data", doc)
    for key in ("videos", "items", "results"):
        if isinstance(node.get(key), list):
            return node[key]
    if isinstance(node.get("data"), dict):
        return videos_of(node["data"])
    return []


def strength(views, followers):
    if not views or not followers or followers <= 0:
        return 0.0
    ratio = views / followers
    if ratio <= 1:
        return 0.0
    return math.log(ratio) * math.log(followers)


def enrich(v):
    a = v.get("author") or {}
    intel = v.get("intelligence") or {}
    views = v.get("views") or 0
    followers = a.get("followers") or 0
    likes = v.get("likes") or 0
    comments = v.get("comments") or 0
    shares = v.get("shares") or 0
    return {
        "url": v.get("url"),
        "platform": v.get("platform"),
        "author": a.get("username"),
        "followers": followers,
        "views": views,
        "ratio": round(views / followers, 1) if followers else 0,
        "strength": round(strength(views, followers), 1),
        "er": round((likes + comments + shares) / views * 100, 2) if views else 0,
        "published": (v.get("publish_date") or "")[:10],
        "keyword": v.get("keyword_found_by"),
        "hook_text": intel.get("hook_text"),
        "hook_type": intel.get("hook_type"),
        "content_format": intel.get("content_format"),
        "visual_format": intel.get("visual_format"),
        "tone": intel.get("emotional_tone"),
        "has_text": intel.get("has_text_overlay"),
        "summary": intel.get("summary"),
        "intel_status": v.get("intelligence_status"),
    }


def dist(rows, field, top=8):
    c = Counter(r[field] for r in rows if r.get(field))
    return c.most_common(top)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    doc = load(sys.argv[1])
    rows = [enrich(v) for v in videos_of(doc)]
    rows = [r for r in rows if r["views"]]
    rows.sort(key=lambda r: r["strength"], reverse=True)

    n = len(rows)
    cut = max(1, n // 4)
    winners, rest = rows[:cut], rows[-cut:]

    out = {
        "всего_роликов": n,
        "с_разметкой": sum(1 for r in rows if r["intel_status"] == "ready"),
        "победителей_в_выборке": len(winners),
        "сила_порог_победителей": winners[-1]["strength"] if winners else 0,
        "площадки": dict(Counter(r["platform"] for r in rows)),
        "форматы_победители": dist(winners, "content_format"),
        "форматы_остальные": dist(rest, "content_format"),
        "хуки_победители": dist(winners, "hook_type"),
        "хуки_остальные": dist(rest, "hook_type"),
        "съёмка_победители": dist(winners, "visual_format"),
        "тон_победители": dist(winners, "tone"),
        "ключи_победители": dist(winners, "keyword"),
        "топ": winners[:15],
    }

    if "--json" in sys.argv:
        path = sys.argv[sys.argv.index("--json") + 1]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print("записано:", path)

    def p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            sys.stdout.buffer.write((s + "\n").encode("utf-8"))

    p(f"роликов {n}, с разметкой {out['с_разметкой']}, площадки {out['площадки']}")
    p(f"порог победителей по силе: {out['сила_порог_победителей']}")
    for key in ("форматы_победители", "форматы_остальные", "хуки_победители",
                "хуки_остальные", "съёмка_победители", "тон_победители"):
        p(f"\n{key}:")
        for name, cnt in out[key]:
            p(f"   {cnt:>3}  {name}")
    p("\nтоп по силе залёта:")
    for r in out["топ"]:
        p(f"  сила {r['strength']:>6} | x{r['ratio']} | {r['views']:>9} просм | "
          f"{r['followers']:>8} подп | ER {r['er']}% | {r['platform']} | {r['published']}")
        p(f"     формат: {r['content_format']} | хук: {r['hook_type']} | {r['visual_format']}")
        if r["hook_text"]:
            p(f"     «{r['hook_text']}»")
        p(f"     {r['url']}")


if __name__ == "__main__":
    main()
