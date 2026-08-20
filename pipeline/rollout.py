"""
Раскатка банка на семь личностей: уникализация, артикул, график публикаций.

Что делает за один запуск:
  1. отбирает из банка ролики, пригодные к публикации;
  2. строит график — кто, что и в какой день выкладывает, с прогревом;
  3. делает каждому ролику семь вариантов, по одному на личность;
  4. накладывает артикул в конце;
  5. раскладывает файлы по папкам дней;
  6. пишет план публикаций в MD.

    python rollout.py --plan            только посчитать и показать график
    python rollout.py --run             сделать файлы
    python rollout.py --run --limit 14  прогон на первых парах, для проверки

Уникализация. Семь приёмов на ролик — по одному каждой личности, чтобы
у одного файла не совпадали ни длительность, ни цвет, ни кадрирование.
Ускорение только на длинных: короткий ролик после него выпадает из минимума
площадок. Зеркалить нельзя — в кадре текст и упаковка.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCT = Path(r"C:\Ferma\factory\products\гель-дюрин")
BANK = PRODUCT / "stock-reels"
CREATORS = PRODUCT / "creators"
FONT = ROOT / "public" / "NotoArm.ttf"

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

# --- личности: код, аккаунт, серийник телефона -------------------------------
PERSONAS = [
    ("CP-01", "shop.bolor_", "R58M24JT50R"),
    ("CP-02", "syunviqa", "RF8M32D7VER"),
    ("CP-03", "dealguide__", "R28M701R6HK"),
    ("CP-04", "marketspy9", "RF8N316NJ5Z"),
    ("CP-05", "valuepick_4", "R39M30RCVWL"),
    ("CP-06", "smartcart_8", "R3CM700SZ8E"),
    ("CP-07", "test_4uu", "R58M21EJS7F"),
]

# --- отбор роликов -----------------------------------------------------------
FOLDERS = ["clean", "subs", "old-clean", "clean-lowres", "duplicates"]
MIN_SEC, MAX_SEC = 8.0, 40.0
MIN_HEIGHT = 1280
# русская линия: этикетка и озвучка на русском, для армянских аккаунтов не идёт
SKIP = {"DYU-ru-oven", "DYU-ru-bathroom"}

# --- артикул -----------------------------------------------------------------
SKU_TEXT = "WB Արտիկուլ։ 287963132"
SKU_TAIL = 3.0          # сколько секунд держится в конце
# Доля высоты кадра. 0.74 клала артикул ровно на строку субтитров — и своих,
# и вшитых в чужие ролики; цифры пропадали. 0.63 — полоса, где текста
# почти никогда нет, и до зоны кнопок площадки ещё далеко.
SKU_Y = 0.63
SKU_SIZE = 58           # крупно: артикул должны прочитать с телефона в ленте

# --- прогрев -----------------------------------------------------------------
START = date(2026, 8, 14)
RAMP = [(5, 1), (7, 2)]  # 5 дней по одному, 7 дней по два, дальше по три
FULL = 3

# --- приёмы уникализации -----------------------------------------------------
# Ускорение годится, только если после него ролик не станет короче 15 секунд.
SPEED_TRICKS = [
    ("speed-110", "setpts=PTS/1.10", "atempo=1.10", 1.10),
    ("speed-120", "setpts=PTS/1.20", "atempo=1.20", 1.20),
    ("speed-130", "setpts=PTS/1.30", "atempo=1.30", 1.30),
]
PLAIN_TRICKS = [
    ("crop-2", "crop=iw*0.98:ih*0.98,scale=1080:1920", "", 1.0),
    ("crop-3b", "crop=iw:ih*0.97:0:0,scale=1080:1920", "", 1.0),
    ("warm", "eq=saturation=1.05:gamma_r=1.03:gamma_b=0.98", "", 1.0),
    ("cool", "eq=saturation=0.96:gamma_b=1.03:gamma_r=0.98", "", 1.0),
    ("crop-warm", "crop=iw*0.98:ih*0.98,scale=1080:1920,eq=saturation=1.04:gamma_r=1.02", "", 1.0),
    ("crop-cool", "crop=iw:ih*0.97:0:0,scale=1080:1920,eq=saturation=0.97:gamma_b=1.02", "", 1.0),
    # Сначала приводим к кадру вывода, и только потом режем в долях от него.
    # Жёсткая рамка 1080×1920 на исходнике 720×1280 больше самого кадра —
    # ffmpeg на этом падает.
    ("zoom-102", "scale=1080:1920,crop=iw/1.02:ih/1.02,scale=1080:1920", "", 1.0),
]


def probe(path: Path) -> tuple[float, int]:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-select_streams", "v:0", "-show_entries", "stream=height",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.split()
    try:
        vals = [float(x) for x in out if x.replace(".", "", 1).isdigit()]
        h = int(max(vals)) if vals else 0
        d = min(vals) if vals else 0.0
        return d, h
    except ValueError:
        return 0.0, 0


def pick_clips() -> list[dict]:
    clips: list[dict] = []
    for folder in FOLDERS:
        d = BANK / folder
        if not d.exists():
            continue
        for f in sorted(d.glob("*.mp4")):
            if f.stem in SKIP:
                continue
            sec, h = probe(f)
            if not (MIN_SEC <= sec <= MAX_SEC) or h < MIN_HEIGHT:
                continue
            clips.append({"path": f, "name": f.stem, "sec": round(sec, 1), "h": h})
    return clips


def tricks_for(sec: float) -> list[tuple[str, str, str, float]]:
    """Семь приёмов под конкретный ролик — по одному на личность."""
    out: list[tuple[str, str, str, float]] = []
    for t in SPEED_TRICKS:
        # после ускорения ролик не должен провалиться ниже минимума площадок
        if sec / t[3] >= 15.0:
            out.append(t)
    for t in PLAIN_TRICKS:
        if len(out) >= len(PERSONAS):
            break
        out.append(t)
    return out[:len(PERSONAS)]


def schedule(clips: list[dict]) -> list[dict]:
    """
    Кто, что и когда публикует.

    Ролик обходит все семь личностей, но не подряд: между двумя выходами
    одного ролика держится максимальная возможная пауза. Считается жадно —
    каждый день каждой личности достаётся тот ролик, который дольше всех
    не выходил и у неё ещё не был.
    """
    n = len(clips)
    last_used = {c["name"]: -99 for c in clips}
    seen: dict[tuple[str, str], bool] = {}
    plan: list[dict] = []

    day = 0
    remaining = n * len(PERSONAS)
    while remaining > 0 and day < 400:
        per_day = FULL
        acc = 0
        for days, k in RAMP:
            if day < acc + days:
                per_day = k
                break
            acc += days

        cur = START + timedelta(days=day)
        for slot in range(per_day):
            # Пауза между выходами одного ролика. Держим максимум, который
            # позволяет запас: при 59 роликах и 21 публикации в день дольше
            # трёх дней ролику не отлежаться физически.
            min_gap = max(int(n / (per_day * len(PERSONAS))), 1)

            for pi, (cp, acc_name, serial) in enumerate(PERSONAS):
                # ролики, которые эта личность ещё не публиковала
                free = [c for c in clips if not seen.get((c["name"], cp))]
                if not free:
                    continue
                # и которые успели отлежаться
                rested = [c for c in free if day - last_used[c["name"]] >= min_gap]
                pool = rested or free
                # самый «отлежавшийся»
                pool.sort(key=lambda c: (last_used[c["name"]], c["name"]))
                pick = pool[0]
                seen[(pick["name"], cp)] = True
                last_used[pick["name"]] = day
                remaining -= 1
                plan.append({
                    "date": cur.isoformat(),
                    "day": day + 1,
                    "cp": cp,
                    "account": acc_name,
                    "serial": serial,
                    "clip": pick["name"],
                    "sec": pick["sec"],
                    "src": str(pick["path"]),
                    "slot": slot + 1,
                })
        day += 1
    return plan


def build_file(item: dict, trick: tuple[str, str, str, float]) -> bool:
    key, vf, af, speed = trick
    out_dir = CREATORS / item["cp"] / "ready" / item["date"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{item['clip']}.mp4"
    if dst.exists():
        return True

    dur = item["sec"] / speed
    start = max(dur - SKU_TAIL, 0.0)
    font = FONT.as_posix().replace(":", "\\:")
    # артикул: белым на тёмной плашке, внизу по центру, последние секунды
    sku = (
        f"drawtext=fontfile='{font}':text='{SKU_TEXT}':"
        f"fontcolor=white:fontsize={SKU_SIZE}:box=1:boxcolor=black@0.72:boxborderw=22:"
        f"x=(w-text_w)/2:y=h*{SKU_Y}:enable='gte(t,{start:.2f})'"
    )
    chain = f"{vf},{sku}" if vf else sku

    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", item["src"],
           "-vf", chain]
    if af:
        cmd += ["-af", af]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(dst)]

    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.stderr.write(f"\n{item['clip']} / {item['cp']}: {r.stderr[-400:]}\n")
        return False
    return True


def write_plan(plan: list[dict]) -> None:
    by_date: dict[str, list[dict]] = {}
    for it in plan:
        by_date.setdefault(it["date"], []).append(it)

    lines = [
        "# План публикаций · гель Дюрин",
        "",
        f"Старт {START.strftime('%d.%m.%Y')} · {len(PERSONAS)} личностей · "
        f"{len({p['clip'] for p in plan})} роликов · {len(plan)} публикаций",
        "",
        "Прогрев: первые 5 дней по одному ролику на личность, следующие 7 дней "
        "по два, дальше по три.",
        "",
        "Каждый ролик уникализирован под свою личность: длительность, кадрирование "
        "и цвет у семи копий разные. В конце каждого — артикул "
        f"`{SKU_TEXT}`.",
        "",
        "---",
        "",
    ]

    for d in sorted(by_date):
        items = by_date[d]
        day_no = items[0]["day"]
        human = date.fromisoformat(d).strftime("%d.%m.%Y")
        lines += [
            f"## {human} · день {day_no} · {len(items)} публикаций",
            "",
            "| Личность | Аккаунт | Телефон | Ролик | Сек | Путь к файлу |",
            "|---|---|---|---|---|---|",
        ]
        for it in sorted(items, key=lambda x: (x["cp"], x["slot"])):
            path = f"creators/{it['cp']}/ready/{it['date']}/{it['clip']}.mp4"
            lines.append(
                f"| {it['cp']} | @{it['account']} | `{it['serial']}` | "
                f"{it['clip']} | {it['sec']:.0f} | `{path}` |"
            )
        lines.append("")

    (CREATORS / "ПЛАН-ПУБЛИКАЦИЙ.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="раскатка банка на семь личностей")
    ap.add_argument("--plan", action="store_true", help="только показать график")
    ap.add_argument("--run", action="store_true", help="сделать файлы")
    ap.add_argument("--limit", type=int, default=0, help="ограничить число файлов")
    args = ap.parse_args()

    clips = pick_clips()
    if not clips:
        print("подходящих роликов не найдено")
        return 1

    plan = schedule(clips)
    days = len({p["date"] for p in plan})
    last = max(p["date"] for p in plan)

    print(f"\nроликов отобрано: {len(clips)}")
    print(f"публикаций:       {len(plan)}")
    print(f"дней:             {days}  ({START.strftime('%d.%m')} — "
          f"{date.fromisoformat(last).strftime('%d.%m.%Y')})")

    # проверка паузы между выходами одного ролика
    seen_day: dict[str, int] = {}
    gaps: list[int] = []
    for it in sorted(plan, key=lambda x: x["day"]):
        if it["clip"] in seen_day:
            gaps.append(it["day"] - seen_day[it["clip"]])
        seen_day[it["clip"]] = it["day"]
    if gaps:
        print(f"\nпауза между выходами одного ролика: "
              f"минимум {min(gaps)} дн, в среднем {sum(gaps) / len(gaps):.1f} дн")
        hist: dict[int, int] = {}
        for g in gaps:
            hist[g] = hist.get(g, 0) + 1
        for g in sorted(hist):
            share = hist[g] / len(gaps) * 100
            print(f"  {g} дн: {hist[g]:>3} случаев ({share:.0f}%)")

    write_plan(plan)
    print(f"план: {CREATORS / 'ПЛАН-ПУБЛИКАЦИЙ.md'}")

    if not args.run:
        print("\n(это только расчёт, файлы не делались — добавь --run)\n")
        return 0

    todo = plan[:args.limit] if args.limit else plan
    per_clip: dict[str, list] = {}
    ok = fail = 0
    print(f"\nделаю {len(todo)} файлов…")

    for i, item in enumerate(todo, 1):
        if item["clip"] not in per_clip:
            per_clip[item["clip"]] = tricks_for(item["sec"])
        tr = per_clip[item["clip"]]
        idx = next(i for i, p in enumerate(PERSONAS) if p[0] == item["cp"])
        if build_file(item, tr[idx % len(tr)]):
            ok += 1
        else:
            fail += 1
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}  готово {ok}, ошибок {fail}")

    print(f"\nготово: {ok}, ошибок: {fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
