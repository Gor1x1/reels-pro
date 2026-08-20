"""
Спека из говорящей головы — со склейками по границам фраз.

Проблема, ради которой это написано: если нарезать говорящую голову на сцены
произвольными таймкодами, склейка попадает на середину слова. Зритель слышит
обрыв, и монтаж выглядит грубым.

Здесь границы сцен берутся из субтитров: склейка ставится **между блоками**,
там, где человек и так делает паузу. Тогда jump-cut читается как приём,
а не как ошибка.

    python autospec.py clip.mp4 --captions src/captions.json --out src/spec.json
    python autospec.py clip.mp4 --captions src/captions.json --max 30 --style neon-night

Сцены собираются длиной 2.5–6 секунд: короче — мельтешит, длиннее — провисает.
Зумы расставляются через сцену, чтобы кадр не стоял на месте.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FFPROBE = shutil.which("ffprobe") or "ffprobe"

MIN_SCENE = 2.5
MAX_SCENE = 6.0
# Сколько держать финал с артикулом. Меньше двух секунд цифры не успевают
# прочитаться и переписаться, больше трёх — зритель уходит.
SKU_TAIL = 3.0


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


def group_blocks(blocks: list[dict], total: float, limit: float) -> list[tuple[float, float]]:
    """
    Собирает блоки субтитров в сцены. Граница сцены — всегда конец блока,
    то есть пауза в речи. Внутри сцены может быть несколько блоков.
    """
    scenes: list[tuple[float, float]] = []
    start = 0.0
    used = 0.0

    for i, b in enumerate(blocks):
        nxt = blocks[i + 1]["start"] if i + 1 < len(blocks) else total
        # режем по середине паузы: так ни одно слово не обрубается
        cut = b["end"] + (nxt - b["end"]) / 2 if nxt > b["end"] else b["end"]
        cut = min(cut, total)
        length = cut - start

        if length < MIN_SCENE and i + 1 < len(blocks):
            continue  # копим дальше, сцена ещё короткая

        # Ограничение работает и на последней сцене: иначе, когда субтитры
        # кончились раньше видео, хвост уезжает в одну сцену на полминуты
        # и ролик провисает.
        if length > MAX_SCENE:
            cut = start + MAX_SCENE
            length = MAX_SCENE

        if used + length > limit:
            break
        scenes.append((round(start, 2), round(length, 2)))
        used += length
        start = cut

    # хвост после последнего субтитра — добираем сценами, пока есть материал
    while start < total - MIN_SCENE and used < limit:
        length = min(MAX_SCENE, total - start, limit - used)
        if length < MIN_SCENE:
            break
        scenes.append((round(start, 2), round(length, 2)))
        used += length
        start += length

    return scenes


def main() -> int:
    ap = argparse.ArgumentParser(description="спека со склейками по границам фраз")
    ap.add_argument("video")
    ap.add_argument("--captions", default=str(ROOT / "src" / "captions.json"))
    ap.add_argument("--out", default=str(ROOT / "src" / "spec.json"))
    ap.add_argument("--src", default="", help="путь к видео внутри public/")
    ap.add_argument("--style", default="neon-night")
    ap.add_argument("--anim", default="glow")
    ap.add_argument("--max", type=float, default=32.0, help="предел длины ролика")
    ap.add_argument("--music", default="music.mp3")
    ap.add_argument("--title", default="", help="титр на хуке")
    ap.add_argument("--sku", default="", help="артикул товара — попадёт в финал")
    ap.add_argument("--brand", default="ԴՅՈՒՐԻՆ", help="титр на финальной сцене")
    ap.add_argument("--platform", default="multi")
    args = ap.parse_args()

    video = Path(args.video)
    if not video.exists():
        print(f"нет видео: {video}")
        return 1

    caps = Path(args.captions)
    if not caps.exists():
        print(f"нет субтитров: {caps}")
        return 1

    blocks = json.loads(caps.read_text(encoding="utf-8-sig"))
    if not blocks:
        print("субтитры пустые — резать не по чему")
        return 1

    total = duration(video)
    rel = args.src or f"src/{video.name}"

    scenes_raw = group_blocks(blocks, total, args.max)
    if not scenes_raw:
        print("не удалось собрать сцены")
        return 1

    scenes: list[dict] = []
    for i, (at, sec) in enumerate(scenes_raw):
        # зум через сцену: кадр не стоит на месте, но и не дёргается постоянно
        zoom = [[0, 1.0], [sec * 0.4, 1.08]] if i % 2 == 0 else [[0, 1.06], [sec * 0.5, 1.0]]
        sc: dict = {
            "type": "hook" if i == 0 else "clip",
            "sec": sec,
            "src": rel,
            "in": at,
            "mute": False,
            "volume": 1.0,
            "zooms": zoom,
        }
        if i == 0:
            sc["isVideo"] = True
            if args.title:
                sc["title"] = args.title
            else:
                # без титра хук остаётся обычным кадром, и субтитры не прячутся
                sc["captions"] = True
        elif i % 3 == 0:
            sc["enter"] = "fade"
        scenes.append(sc)

    # Финал с артикулом. Без него ролик не публикуется: по артикулу покупатель
    # находит товар на маркетплейсе, и правило это жёсткое. Раньше спека из
    # сырья собиралась вообще без CTA — брак уезжал молча, потому что все
    # проверки на нём проходили.
    if args.sku:
        last = scenes[-1]
        tail = min(SKU_TAIL, max(1.6, last["sec"] - 1.2))
        # финал отрезаем от последней сцены, а не удлиняем ролик:
        # сумма длительностей должна остаться равной длине речи
        last["sec"] = round(last["sec"] - tail, 2)
        cta = {
            "type": "cta",
            "sec": round(tail, 2),
            "src": rel,
            "isVideo": True,
            "in": round(last["in"] + last["sec"], 2),
            "mute": False,
            "volume": 1.0,
            "captions": True,
            "line1": args.brand,
            "sku": args.sku,
        }
        if last["sec"] < 1.6:
            # остаток стал огрызком — забираем сцену целиком под финал.
            # Кадр короче полутора секунд зритель не успевает прочитать,
            # и на склейке это читается как сбой, а не как приём.
            cta["in"] = last["in"]
            cta["sec"] = round(last["sec"] + tail, 2)
            scenes.pop()
        scenes.append(cta)

    spec = {
        "tz_id": "", "video_id": "", "article": args.sku,
        "style": args.style,
        "pacing": "normal",
        "lang": "hy",
        "fps": 30,
        "platform": args.platform,
        "captionAnim": args.anim,
        "music": args.music,
        "musicVolume": 0.05,
        "duck": True,
        "_note": "Сцены нарезаны по границам фраз: склейки попадают в паузы речи.",
        "scenes": scenes,
    }

    Path(args.out).write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")

    used = sum(s["sec"] for s in scenes)
    print(f"\nсцен {len(scenes)}, ролик {used:.1f} с из {total:.1f} с исходника")
    for i, s in enumerate(scenes, 1):
        print(f"  {i}. {s['in']:6.2f} → {s['in'] + s['sec']:6.2f}   {s['sec']:4.1f} с")
    print(f"\nспека: {args.out}")
    print("склейки стоят в паузах между фразами — слова не рвутся")
    return 0


if __name__ == "__main__":
    sys.exit(main())
