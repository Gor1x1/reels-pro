"""
Резка говорящей головы по волне звука — встык, без пауз между фразами.

Зачем. Первая сборка резала по границам фраз из распознавания речи, и между
фразами остались паузы: распознавание ошибается в границах на 0.4–0.9 секунды,
а тишина перед второй фразой рилса 1 длилась целую секунду. Владелец режет
в CapCut по-другому — по звуковой дорожке: клип начинается там, где поднялся
голос, и кончается там, где он затих, с поджатием внутрь с обеих сторон,
чтобы кадры шли друг за другом «так-так-так». Скрипт делает то же самое.

    python jumpcut.py raw.mp4 --keep keep.json --out rech.mp4 --edl edl.json
    python jumpcut.py raw.mp4 --keep keep.json --drop 30.2-30.9 --speed 1.15 --out rech.mp4
    python jumpcut.py raw.mp4 --plan                        только показать куски

keep.json — где вообще брать речь: [[22.0, 25.2], [26.3, 29.0], ...]. Без него —
весь файл. Берётся из смыслового разбора: внутри файла бывают дубли и мусор,
которые по волне от речи не отличить.

--drop — куски, которые нельзя оставлять, хотя там звучит голос: взгляд вниз
в листок, фальстарт. Находит их `gaze.py`.

--speed — ускорение всего чистовика с сохранением тона голоса. Рилс смотрится
плотнее на 1.1–1.2×; быстрее голос начинает звучать неестественно.

edl.json — таблица «секунда исходника → секунда чистовика». По ней слои и
титры ставятся на слово, а не на глаз.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

WIN = 0.01  # окно огибающей, 10 мс


def envelope(src: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    w = int(16000 * WIN)
    n = len(x) // w
    rms = np.sqrt((x[: n * w].reshape(n, w) ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms)


def voiced_regions(db: np.ndarray, on: float, off: float, gap: float, min_voice: float) -> list[list[float]]:
    """
    Голос по порогу с гистерезисом: начинается громче `on`, заканчивается,
    когда тише `off`. Паузы короче `gap` — это вдох или стык слов внутри
    фразы, их не режем: иначе речь рассыпается на заикание.
    """
    regions, start = [], None
    for i, v in enumerate(db):
        t = i * WIN
        if start is None and v > on:
            start = t
        elif start is not None and v < off:
            # хвост ведётся до конца затухания, а не до первого провала
            j = i
            while j < len(db) and db[j] < off and (j - i) * WIN < gap:
                j += 1
            if j < len(db) and db[j] >= off and (j - i) * WIN < gap:
                continue
            regions.append([start, t])
            start = None
    if start is not None:
        regions.append([start, len(db) * WIN])

    merged: list[list[float]] = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_voice]


def clip(regions: list[list[float]], zones: list[list[float]] | None, drops: list[list[float]]) -> list[list[float]]:
    out = []
    for a, b in regions:
        spans = [[a, b]]
        if zones:
            spans = [[max(a, za), min(b, zb)] for za, zb in zones if min(b, zb) > max(a, za)]
        for s in spans:
            pieces = [s]
            for da, db_ in drops:
                nxt = []
                for pa, pb in pieces:
                    if db_ <= pa or da >= pb:
                        nxt.append([pa, pb])
                        continue
                    if da > pa:
                        nxt.append([pa, da])
                    if db_ < pb:
                        nxt.append([db_, pb])
                pieces = nxt
            out += [p for p in pieces if p[1] - p[0] > 0.08]
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="резка говорящей головы по волне звука")
    p.add_argument("src")
    p.add_argument("--keep", help="json со списком зон [[a,b],...], где брать речь")
    p.add_argument("--drop", action="append", default=[], help="a-b: выкинуть кусок (взгляд вниз, фальстарт)")
    p.add_argument("--on", type=float, default=-40.0, help="порог начала голоса, дБ")
    p.add_argument("--off", type=float, default=-38.0, help="порог конца голоса, дБ: выше — резче хвост")
    p.add_argument("--gap", type=float, default=0.12, help="паузы короче не режем, с")
    p.add_argument("--pre", type=float, default=0.01, help="запас перед голосом, с")
    p.add_argument("--post", type=float, default=0.02, help="запас после голоса, с")
    p.add_argument("--min-voice", type=float, default=0.1)
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--out")
    p.add_argument("--edl")
    p.add_argument("--plan", action="store_true")
    p.add_argument("--confirm-drop", action="store_true",
                   help="голос вне зон выкинуть намеренно — только по слову владельца (М-27)")
    a = p.parse_args()

    db = envelope(a.src)
    zones = json.loads(Path(a.keep).read_text(encoding="utf-8")) if a.keep else None
    drops = [[float(x) for x in d.split("-")] for d in a.drop]
    regions = voiced_regions(db, a.on, a.off, a.gap, a.min_voice)
    segs = clip(regions, zones, drops)

    # М-27: вся сказанная речь — в ролик. Голос вне зон — стоп, а не молчаливая потеря:
    # 16.09.2026 так выкинули 6.5 с конца рилса 1, распознавание там не разобрало слова.
    if zones:
        def inside(a0, b0):
            return sum(max(0.0, min(b0, zb) - max(a0, za)) for za, zb in zones)
        lost = [(ra, rb) for ra, rb in regions if (rb - ra) - inside(ra, rb) > 0.15]
        lost_sec = sum((rb - ra) - inside(ra, rb) for ra, rb in lost)
        if lost_sec > 0.3:
            print(f"СТОП: голос вне зон — {lost_sec:.1f} с речи не попадёт в ролик:", file=sys.stderr)
            for ra, rb in lost:
                print(f"  {ra:7.2f}-{rb:7.2f}", file=sys.stderr)
            if not a.confirm_drop:
                print("Это речь владельца. Расширь зоны. Выкинуть можно только по его слову: --confirm-drop",
                      file=sys.stderr)
                return 3

    # запас по краям без наложения соседних кусков
    padded = []
    for i, (s, e) in enumerate(segs):
        s2 = max(0.0, s - a.pre)
        e2 = e + a.post
        if padded and s2 < padded[-1][1]:
            s2 = padded[-1][1]
        padded.append([round(s2, 3), round(e2, 3)])

    total = sum(e - s for s, e in padded)
    edl, t = [], 0.0
    for s, e in padded:
        d = (e - s) / a.speed
        edl.append({"src": [s, e], "out": [round(t, 3), round(t + d, 3)]})
        t += d
    print(f"кусков {len(padded)}, речи {total:.2f} с, после ускорения {total / a.speed:.2f} с")
    if a.edl:
        Path(a.edl).write_text(json.dumps({"speed": a.speed, "segments": edl}, indent=1), encoding="utf-8")
    if a.plan or not a.out:
        for x in edl:
            print(f"  {x['src'][0]:7.2f}-{x['src'][1]:7.2f}  ->  {x['out'][0]:6.2f}-{x['out'][1]:6.2f}")
        return 0

    parts, labels = [], []
    for i, (s, e) in enumerate(padded):
        fade = min(0.006, (e - s) / 4)
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS,"
                     f"afade=t=in:st=0:d={fade},afade=t=out:st={e - s - fade:.4f}:d={fade}[a{i}]")
        labels.append(f"[v{i}][a{i}]")
    parts.append("".join(labels) + f"concat=n={len(padded)}:v=1:a=1[vc][ac]")
    if a.speed != 1.0:
        parts.append(f"[vc]setpts=PTS/{a.speed},fps=30[vo]")
        parts.append(f"[ac]atempo={a.speed}[ao]")
        vo, ao = "[vo]", "[ao]"
    else:
        vo, ao = "[vc]", "[ac]"
    graph = ";\n".join(parts)
    gfile = Path(a.out).with_suffix(".filter.txt")
    gfile.write_text(graph, encoding="utf-8")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.src, "-/filter_complex", str(gfile),  # ffmpeg 7+: граф из файла, старый ключ убран в 9
           "-map", vo, "-map", ao, "-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
           "-c:a", "aac", "-b:a", "192k", a.out]
    subprocess.run(cmd, check=True)
    gfile.unlink(missing_ok=True)
    print(f"собрано: {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
