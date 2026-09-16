"""
Стоковые вставки: поиск и скачивание с Pexels и Pixabay.

Зачем. Половина профессионального рилса — это вставки, которых автор не снимал:
город, руки за клавиатурой, деньги, толпа. Снимать их дорого, а на бесплатных
стоках они уже лежат с лицензией на коммерческое использование.

    python stock.py search "smartphone farm" --n 8
    python stock.py search "телефоны" --lang ru --vertical --n 5
    python stock.py get pexels:5561151 --out public/src
    python stock.py grab "city night" --n 3 --out public/src   поиск + скачивание

Ключи берутся из .env рядом с репозиторием (PEXELS_API_KEY, PIXABAY_API_KEY).

Что важно знать про лицензии:
- Pexels и Pixabay разрешают коммерческое использование без указания автора,
  но запрещают продавать сам клип как есть и показывать людей с клипа так,
  будто они рекламируют товар. Для фона и перебивок — можно.
- Pixabay просит кэшировать ответы API сутки: повторный поиск того же запроса
  берётся из runs/stock-cache, а не из сети.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "runs" / "stock-cache"
CACHE_TTL = 24 * 3600  # Pixabay требует сутки


def load_env() -> dict[str, str]:
    """Ключи из .env репозитория, потом из окружения."""
    env: dict[str, str] = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("PEXELS_API_KEY", "PIXABAY_API_KEY"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


def fetch(url: str, headers: dict[str, str] | None = None) -> dict:
    """GET с кэшем на сутки — иначе Pixabay ругается, а Pexels тратит лимит."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    cached = CACHE / f"{key}.json"
    if cached.exists() and time.time() - cached.stat().st_mtime < CACHE_TTL:
        return json.loads(cached.read_text(encoding="utf-8"))

    # Pexels отвечает 403 на стандартный заголовок urllib — представляемся браузером
    head = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) reels-pro/1.0"}
    head.update(headers or {})
    req = urllib.request.Request(url, headers=head)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    cached.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def search_pexels(query: str, n: int, vertical: bool, key: str) -> list[dict]:
    params = {"query": query, "per_page": min(n * 2, 40)}
    if vertical:
        params["orientation"] = "portrait"
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(params)
    data = fetch(url, {"Authorization": key})

    out = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", []) if f.get("width")]
        if not files:
            continue
        # берём лучший файл, который не больше 4K по ширине
        best = max(files, key=lambda f: (f["width"] <= 2160, f["width"]))
        out.append({
            "id": f"pexels:{v['id']}",
            "w": best["width"], "h": best["height"],
            "sec": v.get("duration", 0),
            "author": v.get("user", {}).get("name", ""),
            "page": v.get("url", ""),
            "link": best["link"],
            "thumb": (v.get("video_pictures") or [{}])[len(v.get("video_pictures") or [0]) // 2].get("picture")
                     or v.get("image", ""),
        })
    return out[:n]


def search_pixabay(query: str, n: int, vertical: bool, key: str) -> list[dict]:
    params = {"key": key, "q": query, "per_page": max(min(n * 2, 200), 3),
              "video_type": "film"}
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode(params)
    data = fetch(url)

    out = []
    for v in data.get("hits", []):
        streams = v.get("videos", {})
        best = None
        for name in ("large", "medium", "small"):
            s = streams.get(name)
            if s and s.get("url"):
                best = s
                break
        if not best:
            continue
        w, h = best.get("width", 0), best.get("height", 0)
        if vertical and w >= h:
            continue
        out.append({
            "id": f"pixabay:{v['id']}",
            "w": w, "h": h,
            "sec": v.get("duration", 0),
            "author": v.get("user", ""),
            "page": v.get("pageURL", ""),
            "link": best["url"],
            "thumb": best.get("thumbnail") or streams.get("medium", {}).get("thumbnail", ""),
        })
    return out[:n]


def search(query: str, n: int, vertical: bool, env: dict) -> list[dict]:
    res: list[dict] = []
    if env.get("PEXELS_API_KEY"):
        try:
            res += search_pexels(query, n, vertical, env["PEXELS_API_KEY"])
        except Exception as e:  # сеть или лимит — не роняем поиск целиком
            print(f"  pexels не ответил: {e}", file=sys.stderr)
    if env.get("PIXABAY_API_KEY"):
        try:
            res += search_pixabay(query, n, vertical, env["PIXABAY_API_KEY"])
        except Exception as e:
            print(f"  pixabay не ответил: {e}", file=sys.stderr)
    return res


def download(item: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = item["id"].replace(":", "-") + ".mp4"
    dst = out_dir / name
    if dst.exists():
        return dst
    req = urllib.request.Request(item["link"], headers={"User-Agent": "reels-pro"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dst


def sheet(items: list[dict], out: Path, title: str) -> Path:
    """
    Лист превью кандидатов с номерами. Сток выбирается глазами по смыслу
    бита, а не по первому результату поиска: выдача стоков отвечает на слова
    запроса, а не на то, что происходит в ролике.
    """
    import cv2
    import numpy as np

    cells = []
    for i, it in enumerate(items):
        img = None
        if it.get("thumb"):
            try:
                req = urllib.request.Request(it["thumb"], headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    arr = np.frombuffer(r.read(), np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                img = None
        cell = np.full((426, 240, 3), 40, np.uint8)
        if img is not None:
            h, w = img.shape[:2]
            k = min(240 / w, 426 / h)
            im = cv2.resize(img, (int(w * k), int(h * k)))
            y0, x0 = (426 - im.shape[0]) // 2, (240 - im.shape[1]) // 2
            cell[y0:y0 + im.shape[0], x0:x0 + im.shape[1]] = im
        cv2.rectangle(cell, (0, 0), (240, 30), (0, 0, 0), -1)
        cv2.putText(cell, f"{i+1}  {it['id']}", (6, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (90, 255, 180), 1, cv2.LINE_AA)
        cv2.putText(cell, f"{it['w']}x{it['h']} {it['sec']}s", (6, 416), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
        cells.append(cell)
    cols = 4
    while len(cells) % cols:
        cells.append(np.full((426, 240, 3), 20, np.uint8))
    rows = [np.hstack(cells[i:i + cols]) for i in range(0, len(cells), cols)]
    grid = np.vstack(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), grid)
    out.with_suffix(".json").write_text(json.dumps({"query": title, "items": items}, ensure_ascii=False, indent=2),
                                        encoding="utf-8")
    return out


def print_items(items: list[dict]) -> None:
    for it in items:
        print(f"  {it['id']:<18} {it['w']}x{it['h']}  {it['sec']}s  {it['author']}")
        print(f"      {it['page']}")


def main() -> int:
    p = argparse.ArgumentParser(description="стоковые вставки с Pexels и Pixabay")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="найти и показать")
    s.add_argument("query")
    s.add_argument("--n", type=int, default=6)
    s.add_argument("--vertical", action="store_true", help="только вертикальные")
    s.add_argument("--json", help="записать результат файлом")

    g = sub.add_parser("get", help="скачать по id вида pexels:123")
    g.add_argument("ident")
    g.add_argument("--query", default="", help="запрос, в котором он нашёлся")
    g.add_argument("--out", default="public/src")

    b = sub.add_parser("grab", help="найти и сразу скачать")
    b.add_argument("query")
    b.add_argument("--n", type=int, default=3)
    b.add_argument("--vertical", action="store_true")
    b.add_argument("--out", default="public/src")

    sh = sub.add_parser("sheet", help="лист превью кандидатов — выбирать глазами")
    sh.add_argument("query")
    sh.add_argument("--n", type=int, default=8)
    sh.add_argument("--vertical", action="store_true")
    sh.add_argument("--out", required=True, help="куда положить PNG листа")

    a = p.parse_args()
    env = load_env()
    if not env.get("PEXELS_API_KEY") and not env.get("PIXABAY_API_KEY"):
        print("нет ключей: положи PEXELS_API_KEY и PIXABAY_API_KEY в .env", file=sys.stderr)
        return 2

    if a.cmd == "search":
        items = search(a.query, a.n, a.vertical, env)
        print(f"найдено {len(items)} по запросу «{a.query}»")
        print_items(items)
        if a.json:
            Path(a.json).write_text(json.dumps(items, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        return 0

    if a.cmd == "sheet":
        items = search(a.query, a.n, a.vertical, env)
        dst = sheet(items, Path(a.out), a.query)
        print(f"лист {len(items)} кандидатов: {dst}")
        return 0

    if a.cmd == "get":
        items = search(a.query or a.ident.split(":")[1], 40, False, env)
        found = [i for i in items if i["id"] == a.ident]
        if not found:
            print(f"{a.ident} не найден в выдаче — укажи --query тем же запросом",
                  file=sys.stderr)
            return 1
        dst = download(found[0], Path(a.out))
        print(f"скачано: {dst}")
        return 0

    if a.cmd == "grab":
        items = search(a.query, a.n, a.vertical, env)
        if not items:
            print("ничего не нашлось", file=sys.stderr)
            return 1
        for it in items:
            dst = download(it, Path(a.out))
            print(f"  {it['id']:<18} {it['w']}x{it['h']} -> {dst}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
