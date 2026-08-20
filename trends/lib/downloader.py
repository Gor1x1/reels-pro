# -*- coding: utf-8 -*-
r"""Скачивание чужих роликов для разбора (секция 1, агент ref-downloader).

    python downloader.py <url> [папка] [имя]

Папка задаётся вторым аргументом: runs\<дата>\<товар>\refs.
Без неё — runs\<сегодня>\refs (разбор вне товара). Кладёт видео <имя>.mp4
и метаданные <имя>.meta.json, печатает метаданные JSON в stdout.
yt-dlp сам предпочитает форматы без водяного знака (TikTok/IG).
При ошибке экстрактора первым делом обновить на ночную сборку:
    python -m pip install -U --pre "yt-dlp[default]"
(стабильный канал отстаёт; поломку TikTok 15.08.2026 чинила именно ночная).
Куки Chrome (запасной заход для закрытых роликов) читаются только при
закрытом Chrome — открытый держит базу под замком.
"""
import json
import os
import sys
from datetime import date

try:
    import yt_dlp
except ImportError:
    sys.exit("yt-dlp не установлен: python -m pip install yt-dlp")

# Корень завода. На другой машине задаётся переменной FACTORY_DIR,
# чтобы скрипт работал без правки кода.
FACTORY = os.environ.get("FACTORY_DIR") or r"C:\Ferma\factory"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    url = sys.argv[1]
    # Папку прогона задаёт вызывающий: runs\<дата>\<товар>\refs.
    # Без неё складываем в общий refs дня — разбор вне товара.
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        FACTORY, "runs", date.today().isoformat(), "refs")
    name = sys.argv[3] if len(sys.argv) > 3 else "%(id)s"
    os.makedirs(outdir, exist_ok=True)

    opts = {
        "outtmpl": os.path.join(outdir, name + ".%(ext)s"),
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
    except yt_dlp.utils.DownloadError:
        # Без логина не отдали (приватный/возрастной, чаще Instagram) —
        # повтор с куками залогиненного Chrome владельца
        opts["cookiesfrombrowser"] = ("chrome",)
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            path = ydl.prepare_filename(info)
    base, _ = os.path.splitext(path)
    if not os.path.exists(path) and os.path.exists(base + ".mp4"):
        path = base + ".mp4"

    up = info.get("upload_date") or ""
    meta = {
        "file": path,
        "url": info.get("webpage_url") or url,
        "platform": info.get("extractor_key", "").lower(),
        "title": info.get("title"),
        "author": info.get("uploader") or info.get("channel"),
        "published": f"{up[:4]}-{up[4:6]}-{up[6:]}" if len(up) == 8 else None,
        "views": info.get("view_count"),
        "likes": info.get("like_count"),
        "comments": info.get("comment_count"),
        "duration_sec": info.get("duration"),
    }
    with open(base + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    out = json.dumps(meta, ensure_ascii=False, indent=2)
    try:
        print(out)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(out.encode("utf-8"))


if __name__ == "__main__":
    main()
