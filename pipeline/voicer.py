"""
Озвучка ролика голосом личности.

Работает в два шага, потому что синтез живёт снаружи — в сервисе, где заведены
голоса. Скрипт готовит текст к озвучке и доводит готовый звук до монтажа.

    python voicer.py prepare script.json --cp CP-01
        → текст для вставки в сервис + напоминание, каким голосом читать

    python voicer.py finish script.json --audio voice.mp3 --cp CP-01
        → public/voice.wav (мастеринг) + src/captions.json (тайминги)

Почему субтитры делаются здесь. Текст реплик известен из сценария, и он
написан носителем. Распознавать его заново — значит получить ошибки в кадре.
`finish` берёт у модели только тайминги, а слова ставит из сценария.

Мастеринг: фильтр низов, чистка шума, компрессия, подъём разборчивости
на 3 кГц, громкость −16 LUFS. Именно −16, а не −14: поверх ляжет музыка,
и на сведении финал выйдет ровно −14.
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
PERSONAS = Path(r"C:\Ferma\factory\personas")
FFMPEG = shutil.which("ffmpeg") or "ffmpeg"


def read_script(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def persona(cp: str) -> dict:
    """Достаёт из voice.txt то, что нужно для озвучки."""
    f = PERSONAS / cp / "voice.txt"
    if not f.exists():
        return {}
    txt = f.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for key, pat in (("name", r"·\s*(.+)"), ("phone", r"телефон:\s*(\S+)"),
                     ("speech", r"характер:\s*(.+)"),
                     # только на той же строке: иначе подхватывается
                     # следующий заголовок, когда id ещё не заполнен
                     ("voice_id", r"voice_id\s*=[ \t]*(\S+)[ \t]*$")):
        m = re.search(pat, txt, re.MULTILINE)
        if m:
            out[key] = m.group(1).strip()
    return out


def prepare(script: dict, cp: str, out_dir: Path) -> int:
    lines = [(i, (b.get("line") or "").strip())
             for i, b in enumerate(script.get("beats", []), 1) if b.get("line")]
    if not lines:
        print("в сценарии нет реплик — озвучивать нечего")
        return 1

    p = persona(cp)
    full = " ".join(t for _, t in lines)
    total_sec = sum(float(b.get("sec", 0)) for b in script.get("beats", []))

    out_dir.mkdir(parents=True, exist_ok=True)
    txt = out_dir / f"{script.get('id', 'reel')}-{cp}.txt"

    body = [
        f"# Озвучка · {script.get('id', '')} · {cp}",
        "",
        f"Голос:      {p.get('name', cp)}",
        f"Телефон:    {p.get('phone', '—')}",
        f"Характер:   {p.get('speech', '—')}",
        f"ID голоса:  {p.get('voice_id', 'не задан — заполнить в voice.txt')}",
        "",
        f"Длина монтажа: {total_sec:.1f} с. Озвучка должна уложиться в неё,",
        "иначе последняя сцена оборвётся на полуслове.",
        "",
        "## Текст целиком (для вставки в сервис)",
        "",
        full,
        "",
        "## По битам — если озвучивать частями",
        "",
    ]
    for i, t in lines:
        sec = float(script["beats"][i - 1].get("sec", 0))
        body.append(f"{i}. [{sec:.1f} с] {t}")

    body += [
        "",
        "## Дальше",
        "",
        "Сгенерировать голосом личности, сохранить файл и запустить:",
        "",
        f"    python voicer.py finish <script.json> --audio <файл> --cp {cp}",
    ]

    txt.write_text("\n".join(body), encoding="utf-8")
    print(f"\nтекст для озвучки: {txt}")
    print(f"голос: {p.get('name', cp)} · {p.get('speech', '—')}")
    print(f"уложиться в {total_sec:.1f} с, слов {len(full.split())}\n")
    return 0


def master(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-af",
         "highpass=f=80,afftdn=nf=-25,"
         "acompressor=threshold=-18dB:ratio=3:attack=8:release=180,"
         "equalizer=f=3000:width_type=q:w=1.2:g=2,"
         "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", str(dst)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1200:])
        return False
    return True


def duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error",
         "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def finish(script_path: Path, script: dict, audio: Path, cp: str) -> int:
    voice = ROOT / "public" / "voice.wav"
    if not master(audio, voice):
        print("мастеринг не прошёл")
        return 1

    got = duration(voice)
    want = sum(float(b.get("sec", 0)) for b in script.get("beats", []))
    print(f"\nозвучка: {voice.name}, {got:.1f} с")
    print(f"монтаж:  {want:.1f} с")

    diff = got - want
    if abs(diff) > 0.35:
        print(f"\n  РАСХОЖДЕНИЕ {diff:+.1f} с.")
        if diff > 0:
            print("  Озвучка длиннее монтажа — последняя сцена оборвётся."
                  "\n  Либо удлинить биты в сценарии, либо сократить текст.")
        else:
            print("  Озвучка короче — в конце повиснет тишина."
                  "\n  Либо сократить биты, либо добавить фразу.")
    else:
        print("  сходится")

    # субтитры: слова из сценария, тайминги из звука
    print("\nсобираю субтитры выравниванием…")
    r = subprocess.run(
        [sys.executable, str(ROOT / "pipeline" / "align.py"), str(voice),
         "--script", str(script_path), "--out", str(ROOT / "src" / "captions.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(r.stdout[-900:] if r.stdout else r.stderr[-600:])

    print(f"\nдальше: прописать \"voice\": \"voice.wav\" в спеке и собрать сборкой.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="озвучка ролика голосом личности")
    ap.add_argument("cmd", choices=["prepare", "finish"])
    ap.add_argument("script")
    ap.add_argument("--cp", required=True, help="личность: CP-01 … CP-07")
    ap.add_argument("--audio", help="готовый файл озвучки (для finish)")
    ap.add_argument("--out-dir", default=str(ROOT / "runs" / "voice"))
    args = ap.parse_args()

    sp = Path(args.script)
    if not sp.exists():
        print(f"нет сценария: {sp}")
        return 1
    script = read_script(sp)

    if args.cmd == "prepare":
        return prepare(script, args.cp, Path(args.out_dir))

    if not args.audio or not Path(args.audio).exists():
        print("нужен --audio с файлом озвучки")
        return 1
    return finish(sp, script, Path(args.audio), args.cp)


if __name__ == "__main__":
    sys.exit(main())
