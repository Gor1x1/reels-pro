"""
Папки семи личностей фермы и раскладка голосов по ним.

Каждой личности нужен свой голос, иначе семь аккаунтов звучат одинаково —
и площадки, и зрители связывают их между собой. Файл голоса называется
по серийнику телефона: так сразу видно, чей это голос и на каком устройстве
он публикуется.

    python personas.py init                 — создать папки семи личностей
    python personas.py assign <ключ> CP-03  — положить голос личности
    python personas.py show                 — что у кого есть

Карта личностей взята из анкеты `factory/personas/anketa блгер ферма.md`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(r"C:\Ferma\factory\personas")
VOICES = Path(r"C:\Ferma\factory\products\гель-дюрин\voices")

# CP · аккаунт · имя · серийник · как говорит (из анкеты)
PERSONAS: dict[str, dict[str, str]] = {
    "CP-01": {"acc": "shop.bolor_", "name": "Siranush Yoryan", "serial": "R58M24JT50R",
              "device": "SM-G975F",
              "speech": "спокойная, ровный темп, пауза перед выводом; самая взрослая"},
    "CP-02": {"acc": "syunviqa", "name": "Vika Suqiasyan", "serial": "RF8M32D7VER",
              "device": "SM-G973F",
              "speech": "разговорная на «ты», короткие фразы, живой темп, интонация вверх"},
    "CP-03": {"acc": "dealguide__", "name": "Elena Yoon", "serial": "R28M701R6HK",
              "device": "SM-G9730",
              "speech": "плавная, красивая, медленнее остальных, длинные фразы"},
    "CP-04": {"acc": "marketspy9", "name": "Rozza Shekunc", "serial": "RF8N316NJ5Z",
              "device": "SM-G973F",
              "speech": "резковатая, конкретная, рубленые фразы, быстрый темп"},
    "CP-05": {"acc": "valuepick_4", "name": "Kima Avanesyan", "serial": "R39M30RCVWL",
              "device": "SM-G973F",
              "speech": "обычная разговорная без стараний, средние фразы, спокойный темп"},
    "CP-06": {"acc": "smartcart_8", "name": "Kima Ashotyan", "serial": "R3CM700SZ8E",
              "device": "SM-G977N",
              "speech": "быстрая, инструктивная, повелительное наклонение"},
    "CP-07": {"acc": "test_4uu", "name": "Nune Ananyan", "serial": "R58M21EJS7F",
              "device": "SM-G973F",
              "speech": "живая, с подколами, очень короткие фразы, самый быстрый темп"},
}

VOICE_TXT = """# Голос личности {cp} · {name}

аккаунт:   @{acc}
телефон:   {serial} ({device})
характер:  {speech}

образец:   {sample}
источник:  {source}

## ID клона

Заполнить после клонирования — сюда идёт идентификатор голоса из сервиса.
По нему `voicer` синтезирует реплики этой личности.

    voice_id =

## Правило

Голос закрепляется за личностью навсегда. Сменить его потом нельзя:
подписчики узнают канал по голосу, и смена читается как смена автора.
"""


def init() -> int:
    for cp, p in PERSONAS.items():
        d = ROOT / cp
        d.mkdir(parents=True, exist_ok=True)
        txt = d / "voice.txt"
        if not txt.exists():
            txt.write_text(
                VOICE_TXT.format(cp=cp, sample="— не назначен —", source="—", **p),
                encoding="utf-8",
            )
    print(f"папки семи личностей готовы: {ROOT}")
    return 0


def assign(key: str, cp: str) -> int:
    if cp not in PERSONAS:
        print(f"нет такой личности: {cp}")
        return 1
    src = VOICES / f"{key}.wav"
    if not src.exists():
        print(f"нет образца: {src}")
        return 1

    p = PERSONAS[cp]
    d = ROOT / cp
    d.mkdir(parents=True, exist_ok=True)
    # имя по серийнику телефона: сразу видно, чей голос и где публикуется
    dst = d / f"voice-{p['serial']}.wav"
    shutil.copy2(src, dst)

    (d / "voice.txt").write_text(
        VOICE_TXT.format(cp=cp, sample=dst.name, source=f"банк роликов, образец «{key}»", **p),
        encoding="utf-8",
    )
    print(f"{cp} · {p['name']} · {p['serial']}  ←  {key}")
    return 0


def show() -> int:
    print(f"\n{'личность':<8} {'аккаунт':<14} {'телефон':<13} голос")
    print("-" * 74)
    for cp, p in PERSONAS.items():
        d = ROOT / cp
        wav = next(d.glob("voice-*.wav"), None) if d.exists() else None
        mark = wav.name if wav else "— нет —"
        print(f"{cp:<8} @{p['acc']:<13} {p['serial']:<13} {mark}")
    print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="личности и их голоса")
    ap.add_argument("cmd", choices=["init", "assign", "show"])
    ap.add_argument("key", nargs="?", help="ключ образца голоса")
    ap.add_argument("cp", nargs="?", help="личность: CP-01 … CP-07")
    args = ap.parse_args()

    if args.cmd == "init":
        return init()
    if args.cmd == "show":
        return show()
    if not args.key or not args.cp:
        print("нужно: assign <ключ голоса> <CP-0X>")
        return 1
    return assign(args.key, args.cp)


if __name__ == "__main__":
    sys.exit(main())
