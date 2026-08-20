"""
Проверка спецификации до рендера. Рендер стоит минуты, ошибка в таймкоде
видна только на готовом файле — дешевле поймать её здесь.

    python validate.py                       — проверить src/spec.json
    python validate.py --spec other.json --captions other-captions.json

Что ловит:
  · нет файла, на который ссылается сцена;
  · кусок выходит за конец исходника — на экране будет замерший кадр;
  · накладка не помещается в свою сцену;
  · длительность ролика вне 15–40 секунд;
  · субтитры выходят за пределы ролика или наезжают на титры CTA;
  · длина озвучки не совпадает с суммой сцен;
  · неизвестный стиль, темп или анимация субтитров.

Отличает ошибки от предупреждений: ошибка означает брак, предупреждение —
повод посмотреть глазами.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

MIN_SEC, MAX_SEC = 15.0, 40.0
# знаков в секунду — скорость чтения текста с экрана телефона
READ_CPS = 15.0

# те же служебные слова, что и при нарезке: блок, заканчивающийся на них,
# читается как оборванная мысль
try:
    from script2spec import TAIL_BAD
except ImportError:  # запуск из другой папки
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from script2spec import TAIL_BAD

STYLES = {"warm-studio", "bold-orange", "clean-minimal", "neon-night",
          "fresh-mint", "soft-cream", "mono-punch", "night-gold"}
PACINGS = {"calm", "normal", "fast", "punch"}
ANIMS = {"karaoke", "word-pop", "blur-in", "mask-wipe", "typewriter",
         "highlight", "stagger-up", "glow", "zoom-punch"}
PLATFORMS = {"tiktok", "instagram", "shorts", "vk", "ok", "likee", "facebook", "multi"}

_durations: dict[str, float | None] = {}


def duration(rel: str) -> float | None:
    """Длительность файла из public/. None — файла нет или он не читается."""
    if rel in _durations:
        return _durations[rel]
    path = PUBLIC / rel
    if not path.exists():
        _durations[rel] = None
        return None
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        _durations[rel] = float(out)
    except ValueError:
        _durations[rel] = None
    return _durations[rel]


def scene_sec(sc: dict, fps: int) -> float:
    if "sec" in sc:
        return float(sc["sec"])
    return float(sc.get("dur", fps)) / fps


def check(spec: dict, captions: list) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    fps = int(spec.get("fps", 30))
    lang = spec.get("lang", "hy")

    if spec.get("style") and spec["style"] not in STYLES:
        errors.append(f"неизвестный стиль «{spec['style']}»; есть: {', '.join(sorted(STYLES))}")
    if spec.get("pacing") and spec["pacing"] not in PACINGS:
        errors.append(f"неизвестный темп «{spec['pacing']}»; есть: {', '.join(sorted(PACINGS))}")
    if spec.get("captionAnim") and spec["captionAnim"] not in ANIMS:
        errors.append(f"неизвестная анимация субтитров «{spec['captionAnim']}»")
    if spec.get("platform") and spec["platform"] not in PLATFORMS:
        errors.append(f"неизвестная площадка «{spec['platform']}»")

    scenes = spec.get("scenes") or []
    if not scenes:
        errors.append("в спеке нет ни одной сцены")
        return errors, warns

    total = 0.0
    cta_windows: list[tuple[float, float]] = []

    for i, sc in enumerate(scenes, 1):
        sec = scene_sec(sc, fps)
        start = total
        total += sec
        kind = sc.get("type", "?")
        tag = f"сцена {i} ({kind})"

        if sec <= 0:
            errors.append(f"{tag}: нулевая длительность")

        if kind == "cta" or (kind == "hook" and sc.get("title")):
            cta_windows.append((start, start + sec))

        # источники сцены: у compare их два
        sources: list[tuple[str, float]] = []
        if kind in ("clip", "broll", "hook") and sc.get("src"):
            sources.append((sc["src"], float(sc.get("in", 0) or 0)))
        if kind == "compare":
            for side in ("before", "after"):
                s = sc.get(side) or {}
                if s.get("src"):
                    sources.append((s["src"], 0.0))
        if kind == "speaker" and spec.get("video"):
            sources.append((spec["video"], 0.0))

        # при замедлении за N секунд сцены проигрывается меньше исходника,
        # при ускорении — больше; без этого проверка границы врёт
        speed = float(sc.get("speed", 1) or 1)

        for rel, offset in sources:
            d = duration(rel)
            if d is None:
                errors.append(f"{tag}: нет файла public/{rel}")
                continue
            # главная ловушка: кусок длиннее того, что осталось в исходнике
            need = offset + sec * speed
            if need > d + 0.05:
                errors.append(
                    f"{tag}: {rel} длится {d:.1f} с, а нужен кусок до {need:.1f} с "
                    f"(in={offset:.1f} + {sec:.1f}×{speed:g}) — в кадре останется "
                    f"замершая картинка"
                )
            elif need > d - 0.2:
                warns.append(f"{tag}: {rel} кончается почти вплотную ({d:.1f} с), запаса нет")

        for j, ov in enumerate(sc.get("overlays") or [], 1):
            at = float(ov.get("at", 0) or 0)
            dur = float(ov.get("dur", 0) or 0)
            if dur <= 0:
                errors.append(f"{tag}: накладка {j} ({ov.get('kind')}) без длительности")
            if at + dur > sec + 0.05:
                errors.append(
                    f"{tag}: накладка {j} ({ov.get('kind')}) идёт до {at + dur:.1f} с "
                    f"при длине сцены {sec:.1f} с — оборвётся"
                )
            if ov.get("kind") == "pointer":
                for axis in ("x", "y"):
                    v = float(ov.get(axis, 0.5))
                    if not 0.05 <= v <= 0.95:
                        warns.append(f"{tag}: указатель {axis}={v} у самого края кадра")
            if ov.get("kind") == "name" and not (spec.get("brand") or {}).get("name"):
                warns.append(f"{tag}: накладка name без brand.name — ничего не покажется")

    if total < MIN_SEC:
        errors.append(f"ролик {total:.1f} с — короче минимума {MIN_SEC:.0f} с")
    elif total > MAX_SEC:
        errors.append(f"ролик {total:.1f} с — длиннее максимума {MAX_SEC:.0f} с")

    # звук
    for key in ("music", "voice"):
        rel = spec.get(key)
        if rel and duration(rel) is None:
            errors.append(f"нет файла public/{rel} ({key})")

    music = spec.get("music")
    if music:
        d = duration(music)
        if d is not None and d < total - 0.2:
            # трек зациклится, и на шве будет слышен обрыв такта
            warns.append(
                f"музыка {d:.1f} с короче ролика {total:.1f} с — трек зациклится со швом. "
                f"Сгенерировать под длину: music.py --sec {total:.0f}"
            )

    voice = spec.get("voice")
    if voice:
        d = duration(voice)
        if d is not None and abs(d - total) > 0.35:
            warns.append(
                f"озвучка {d:.1f} с, монтаж {total:.1f} с — разойдутся на {abs(d - total):.1f} с"
            )
        # дакинг вычисляется по субтитрам: без них музыка не проседает под речь
        if spec.get("music") and spec.get("duck", True) and not captions:
            warns.append(
                "есть озвучка и музыка, но нет субтитров — приглушать музыку не по чему, "
                "музыка будет играть в полную громкость поверх голоса"
            )

    for i, s in enumerate(spec.get("sfx") or [], 1):
        rel = s.get("src")
        if rel and duration(rel) is None:
            errors.append(f"эффект {i}: нет файла public/{rel}")
        if float(s.get("at", 0) or 0) > total:
            warns.append(f"эффект {i} стоит на {s['at']} с — за концом ролика")

    # субтитры
    for i, (a, b) in enumerate(zip(captions, captions[1:]), 1):
        if b["start"] < a["end"] - 0.02:
            warns.append(
                f"субтитры {i} и {i + 1} перекрываются "
                f"({a['end']:.2f} и {b['start']:.2f} с) — на экране будут мигать два блока"
            )

    for i, b in enumerate(captions, 1):
        if b["end"] > total + 0.3:
            warns.append(f"субтитр {i} кончается на {b['end']:.1f} с — за концом ролика")
        for f, t in cta_windows:
            if b["start"] < t and b["end"] > f:
                warns.append(
                    f"субтитр {i} ({b['start']:.1f}–{b['end']:.1f} с) попадает на сцену "
                    f"с крупным титром — он скрыт автоматически, проверь, что так и задумано"
                )
                break
        words = b.get("words") or []
        if not words:
            errors.append(f"субтитр {i}: нет слов")
            continue
        if len(words) > 7:
            warns.append(f"субтитр {i}: {len(words)} слов в блоке — не успеет прочитаться")

        # успевает ли зритель прочитать: блок висит до следующего, но если
        # следующий начинается сразу, времени на чтение остаётся только своё
        text = " ".join(w["t"] for w in words)
        span = b["end"] - b["start"]
        need = len(text) / READ_CPS
        if span + 0.3 < need:
            warns.append(
                f"субтитр {i} «{text[:32]}…»: {span:.1f} с на {len(text)} знаков — "
                f"нужно около {need:.1f} с, читаться не успеет"
            )

        # обрыв мысли: блок кончается союзом или предлогом
        last = re.sub(r"[^\w԰-֏]", "", words[-1]["t"].lower())
        if last in TAIL_BAD.get(lang, set()):
            warns.append(
                f"субтитр {i} заканчивается на «{words[-1]['t']}» — фраза читается "
                f"оборванной, перенеси это слово в следующий блок"
            )

    return errors, warns


def main() -> int:
    ap = argparse.ArgumentParser(description="проверка спеки до рендера")
    ap.add_argument("--spec", default=str(ROOT / "src" / "spec.json"))
    ap.add_argument("--captions", default=str(ROOT / "src" / "captions.json"))
    args = ap.parse_args()

    spec_path, cap_path = Path(args.spec), Path(args.captions)
    if not spec_path.exists():
        print(f"нет файла спеки: {spec_path}")
        return 1

    # utf-8-sig, а не utf-8: редакторы Windows сохраняют JSON с BOM, и на
    # обычном utf-8 разбор падает на первом символе
    raw = spec_path.read_text(encoding="utf-8-sig")
    # в спеке допускаются комментарии — их пишут в примерах
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    spec = json.loads(raw)
    captions = json.loads(cap_path.read_text(encoding="utf-8-sig")) if cap_path.exists() else []

    errors, warns = check(spec, captions)

    total = sum(scene_sec(s, int(spec.get("fps", 30))) for s in spec.get("scenes", []))
    print(f"\nспека: {spec_path.name} · {len(spec.get('scenes', []))} сцен · {total:.1f} сек · "
          f"стиль {spec.get('style', 'warm-studio')} · темп {spec.get('pacing', 'из стиля')}\n")

    for w in warns:
        print(f"  внимание  {w}")
    for e in errors:
        print(f"  ОШИБКА    {e}")

    if not errors and not warns:
        print("  всё чисто, можно рендерить")
    elif not errors:
        print(f"\nошибок нет, предупреждений {len(warns)} — рендерить можно")
    else:
        print(f"\nошибок {len(errors)} — рендер даст брак, сначала исправить")
    print()

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
