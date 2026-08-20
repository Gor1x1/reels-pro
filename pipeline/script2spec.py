"""
Сценарий → монтаж. Берёт `script.json` от сценариста и собирает из него
`spec.json` и `captions.json` — то, что понимает движок сборки.

    python script2spec.py runs/2026-08-12/M1-K1-ГЕЛ-001/script.json
    python script2spec.py script.json --out-dir src --dry

Главное здесь — разбивка реплик на субтитры. Резать по счёту слов нельзя:
блок обрывается на предлоге, и зритель читает незаконченную мысль. Границы
ищутся по знакам препинания, потом по служебным словам, и только в последнюю
очередь по длине.

Формат сценария — см. раздел «Сценарий» в SKILL.md. Минимум на бит:
роль, длительность и реплика; источник можно проставить позже.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Роль бита в сюжете → тип сцены движка.
ROLE_SCENE = {
    "hook": "hook",
    "problem": "clip",
    "solution": "clip",
    "demo": "clip",
    "proof": "clip",
    "step": "clip",
    "offer": "clip",
    "compare": "compare",
    "cta": "cta",
}

# Служебные слова, на которых блок субтитров заканчивать нельзя: строка
# «мне это не помогло и» читается как оборванная, даже если пауза там есть.
TAIL_BAD = {
    "hy": {"և", "ու", "որ", "թե", "բայց", "կամ", "իսկ", "ապա", "որպեսզի", "երբ", "եթե", "քան",
           # «մի քանի» = «несколько»: блок, кончающийся на «մի», читается оборванным
           "մի", "շատ", "ամեն", "այս", "այդ", "այն", "իր", "մեր", "ձեր", "նրա"},
    "ru": {"и", "а", "но", "или", "что", "чтобы", "как", "когда", "если", "для", "на", "в",
           "с", "по", "за", "от", "до", "из", "у", "к", "о", "же", "бы", "ли", "не"},
    "en": {"and", "or", "but", "that", "if", "when", "for", "to", "in", "on", "of", "the", "a"},
}

# Сильные границы — здесь мысль точно закончена.
STRONG = re.compile(r"[.!?։；;:]+")
# Слабые — годятся, если блок иначе получается длинным.
WEAK = re.compile(r"[,،—–-]+")

MAX_CHARS = 58        # две строки по ~29 знаков
MAX_WORDS = 6
MIN_WORDS = 2
READ_CPS = 15.0       # знаков в секунду — скорость чтения с экрана
MIN_BLOCK_SEC = 1.1


def words_of(text: str) -> list[str]:
    return [w for w in re.split(r"\s+", text.strip()) if w]


def bare(word: str) -> str:
    return re.sub(r"[^\w԰-֏]", "", word.lower())


def split_line(line: str, lang: str) -> list[list[str]]:
    """
    Режет реплику на блоки субтитров по смыслу.

    Порядок: сильные знаки → слабые знаки → длина. Блок не заканчивается
    служебным словом и не остаётся из одного слова, если этого можно избежать.
    """
    tail_bad = TAIL_BAD.get(lang, TAIL_BAD["ru"])

    # 1. режем по сильным знакам — эти границы бесспорны
    chunks = [c.strip() for c in STRONG.split(line) if c.strip()]
    blocks: list[list[str]] = []

    for chunk in chunks:
        ws = words_of(chunk)
        if not ws:
            continue
        if len(" ".join(ws)) <= MAX_CHARS and len(ws) <= MAX_WORDS:
            blocks.append(ws)
            continue

        # 2. длинный кусок — пробуем по слабым знакам
        parts = [p.strip() for p in WEAK.split(chunk) if p.strip()]
        for part in parts:
            pw = words_of(part)
            if not pw:
                continue
            if len(" ".join(pw)) <= MAX_CHARS and len(pw) <= MAX_WORDS:
                blocks.append(pw)
                continue

            # 3. всё ещё длинно — режем по длине, но границу двигаем назад,
            #    пока блок не перестанет заканчиваться служебным словом
            cur: list[str] = []
            for w in pw:
                probe = cur + [w]
                if len(" ".join(probe)) > MAX_CHARS or len(probe) > MAX_WORDS:
                    carry: list[str] = []
                    while len(cur) > MIN_WORDS and bare(cur[-1]) in tail_bad:
                        carry.insert(0, cur.pop())
                    if cur:
                        blocks.append(cur)
                    cur = carry + [w]
                else:
                    cur = probe
            if cur:
                blocks.append(cur)

    # 4. одинокое слово в конце прилепляем к предыдущему блоку
    merged: list[list[str]] = []
    for b in blocks:
        if merged and len(b) < MIN_WORDS and len(" ".join(merged[-1] + b)) <= MAX_CHARS + 8:
            merged[-1] = merged[-1] + b
        else:
            merged.append(b)
    return merged


def time_blocks(blocks: list[list[str]], start: float, dur: float) -> list[dict]:
    """
    Раскладывает блоки по времени внутри бита пропорционально длине текста.
    Пословные тайминги нужны караоке-анимациям, поэтому считаются здесь же.

    Если к ролику есть озвучка, тайминги надо брать из неё — это приближение
    под монтаж без голоса.
    """
    total_chars = sum(len(" ".join(b)) for b in blocks) or 1
    out: list[dict] = []
    t = start
    end_limit = start + dur

    for i, b in enumerate(blocks):
        chars = len(" ".join(b))
        share = dur * chars / total_chars
        # не быстрее, чем человек успевает прочитать
        need = max(chars / READ_CPS, MIN_BLOCK_SEC)
        span = max(share, min(need, dur))

        # Блок не должен вылезать за свой бит: иначе он перекроет первый блок
        # следующей сцены, и на экране два субтитра начнут мигать друг сквозь
        # друга. Оставшимся блокам делим то, что осталось до конца бита.
        left = end_limit - t
        rest = len(blocks) - i
        if span > left:
            span = max(left / rest, 0.35) if rest > 1 else max(left, 0.35)

        words = []
        wt = t
        wchars = sum(len(w) for w in b) or 1
        for w in b:
            wd = span * len(w) / wchars
            words.append({"t": w, "s": round(wt, 2), "e": round(wt + wd, 2)})
            wt += wd

        out.append({"start": round(t, 2), "end": round(wt, 2), "words": words})
        t += span

    return out


def snap_to_beat(sec: float, bpm: float, fps: int) -> float:
    """
    Подгоняет длительность сцены под сетку долей музыки.

    Склейка, попавшая в удар, читается как намеренная, мимо удара — как
    оплошность монтажёра. Приём старый и работает на любом материале:
    зритель не осознаёт ритм, но чувствует собранность.

    Округляем к ближайшей половине доли — целые доли дают слишком грубый шаг
    на коротких сценах, четверти уже неразличимы.
    """
    if bpm <= 0:
        return sec
    half = 30.0 / bpm
    beats = max(round(sec / half), 1)
    return round(beats * half * fps) / fps


def build(script: dict) -> tuple[dict, list[dict], list[str]]:
    notes: list[str] = []
    lang = script.get("lang", "hy")
    fps = int(script.get("fps", 30))
    # темп музыки: если задан, длительности сцен встают на сетку долей
    bpm = float(script.get("bpm", 0) or 0)

    spec: dict = {
        # идентификаторы: по ним ролик находит свою строку в таблице
        "tz_id": script.get("id", ""),
        "video_id": script.get("video_id", script.get("id", "")),
        "article": str(script.get("sku", script.get("article", ""))),
        "style": script.get("style", "fresh-mint"),
        "lang": lang,
        "fps": fps,
        "platform": script.get("platform", "multi"),
        "captionAnim": script.get("captionAnim", "word-pop"),
        "duck": True,
        "musicVolume": script.get("musicVolume", 0.08),
        "scenes": [],
    }
    if script.get("pacing"):
        spec["pacing"] = script["pacing"]
    if script.get("music"):
        spec["music"] = script["music"]
    if script.get("voice"):
        spec["voice"] = script["voice"]
    if script.get("brand"):
        spec["brand"] = script["brand"]

    captions: list[dict] = []
    at = 0.0

    for i, beat in enumerate(script.get("beats", []), 1):
        role = beat.get("role", "demo")
        kind = ROLE_SCENE.get(role, "clip")
        sec = float(beat.get("sec", 3.0))
        if bpm and beat.get("snap") is not False:
            snapped = snap_to_beat(sec, bpm, fps)
            if abs(snapped - sec) > 0.005:
                notes.append(f"бит {i} ({role}): {sec:.2f} → {snapped:.2f} с, склейка в такт")
            sec = snapped
        scene: dict = {"type": kind, "sec": round(sec, 3)}

        src = beat.get("source") or {}
        if kind == "compare":
            before, after = beat.get("before") or {}, beat.get("after") or {}
            if not before.get("src") or not after.get("src"):
                notes.append(f"бит {i} ({role}): для сравнения нужны before.src и after.src")
            scene["before"] = {"isVideo": True, **before}
            scene["after"] = {"isVideo": True, **after}
        elif src.get("src"):
            scene["src"] = src["src"]
            if src.get("in") is not None:
                scene["in"] = float(src["in"])
            if kind in ("hook", "cta"):
                scene["isVideo"] = True
        else:
            notes.append(
                f"бит {i} ({role}): нет источника — подставь src и in "
                f"после разбора материала. Кадр по сценарию: {beat.get('shot', '—')}"
            )

        if beat.get("enter"):
            scene["enter"] = beat["enter"]
        if beat.get("zooms"):
            scene["zooms"] = beat["zooms"]
        # сдвиг кадра — им убирают чужие вшитые субтитры из готовых рилсов
        if beat.get("pan"):
            scene["pan"] = beat["pan"]
        # заглушка поверх чужого текста там, где сдвиг не помогает
        if beat.get("cover"):
            scene["cover"] = beat["cover"]
        if beat.get("mute") is False:
            scene["mute"] = False
            if beat.get("volume") is not None:
                scene["volume"] = beat["volume"]
        if beat.get("overlays"):
            scene["overlays"] = beat["overlays"]
        if beat.get("label"):
            scene["label"] = beat["label"]

        # крупный текст на экране
        if kind == "hook" and beat.get("onscreen"):
            scene["title"] = beat["onscreen"]
        if kind == "cta":
            lines = (beat.get("onscreen") or "").split("\n")
            scene["line1"] = lines[0] if lines and lines[0] else "ПОДПИШИСЬ"
            if len(lines) > 1:
                scene["line2"] = lines[1]
            # артикул берётся из шапки сценария, если не задан на бите
            sku = beat.get("sku") or script.get("sku")
            if sku:
                scene["sku"] = str(sku)

        spec["scenes"].append(scene)

        # субтитры бита
        line = (beat.get("line") or "").strip()
        if line and kind != "cta":
            blocks = split_line(line, lang)
            timed = time_blocks(blocks, at, sec)
            over = timed[-1]["end"] - (at + sec) if timed else 0
            if over > 0.25:
                notes.append(
                    f"бит {i} ({role}): реплика не помещается в {sec:.1f} с — "
                    f"нужно ещё {over:.1f} с или короче текст"
                )
            captions.extend(timed)

        at += sec

    if at < 15 or at > 40:
        notes.append(f"весь ролик {at:.1f} с — за пределами 15–40 с, площадки такое режут")

    return spec, captions, notes


def main() -> int:
    ap = argparse.ArgumentParser(description="сценарий → спека монтажа")
    ap.add_argument("script")
    ap.add_argument("--out-dir", default=str(ROOT / "src"))
    ap.add_argument("--dry", action="store_true", help="показать, но не записывать")
    args = ap.parse_args()

    path = Path(args.script)
    if not path.exists():
        print(f"нет файла сценария: {path}")
        return 1

    # utf-8-sig: сценарий мог быть сохранён редактором Windows, то есть с BOM
    script = json.loads(path.read_text(encoding="utf-8-sig"))
    spec, captions, notes = build(script)

    total = sum(s["sec"] for s in spec["scenes"])
    print(f"\n{script.get('id', path.stem)} · {len(spec['scenes'])} сцен · {total:.1f} сек · "
          f"стиль {spec['style']} · субтитров {len(captions)}\n")

    for i, (sc, beat) in enumerate(zip(spec["scenes"], script.get("beats", [])), 1):
        src = sc.get("src", "—")
        print(f"  {i}. {beat.get('role', '?'):<9} {sc['sec']:>4.1f} с  {sc['type']:<8} {src}")

    if notes:
        print()
        for n in notes:
            print(f"  внимание  {n}")

    if args.dry:
        print("\n(пробный прогон, ничего не записано)\n")
        return 0

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "captions.json").write_text(json.dumps(captions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nзаписано: {out / 'spec.json'} и {out / 'captions.json'}")
    print("дальше: python pipeline/validate.py, потом .\\build.ps1\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
