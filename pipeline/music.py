"""
Музыка под ролик. Своя, а не из библиотеки площадки.

Зачем своя. На семи сетях и тысячах публикаций чужой трек — это два риска
сразу: YouTube глушит звук по Content ID, Instagram снимает аудио с рилса.
Трек из библиотеки TikTok лицензирован только внутри TikTok, скачать его
и положить в файл нельзя. Свой сгенерированный трек снимает вопрос целиком.

    python music.py --sec 28 --mood energetic --out public/music.mp3
    python music.py --sec 28 --mood calm --bpm 92 --seed 7 --out track.wav
    python music.py --bank 12 --sec 30 --out-dir library/   — банк на выбор

Движок по умолчанию синтезирует трек сам, без единой зависимости: барабаны,
бас и арпеджио в минорной пентатонике, с сайдчейном под бочку. Это фоновый
ритм под голос — на 7–8 % громкости он держит темп и не спорит с речью.

Если в системе стоит audiocraft, ключ --engine musicgen даёт живое звучание
вместо синтеза. Ставится отдельно и весит несколько гигабайт, поэтому
по умолчанию не используется.
"""

from __future__ import annotations

import argparse
import math
import random
import shutil
import struct
import subprocess
import sys
import wave
from pathlib import Path

SR = 44100

# Настроения задают темп, тональность и плотность аранжировки.
MOODS: dict[str, dict] = {
    "energetic": {"bpm": 128, "scale": [0, 3, 5, 7, 10], "root": 55.0, "hats": 4, "drive": 0.9,
                  "desc": "плотный ритм, для распаковки и теста на себе"},
    "uplifting": {"bpm": 112, "scale": [0, 2, 4, 7, 9], "root": 65.4, "hats": 2, "drive": 0.7,
                  "desc": "светлый мажор, для до/после и результата"},
    "calm": {"bpm": 92, "scale": [0, 2, 3, 7, 8], "root": 49.0, "hats": 2, "drive": 0.45,
             "desc": "спокойный фон, для обзора и объяснения"},
    "tense": {"bpm": 104, "scale": [0, 1, 5, 7, 8], "root": 43.7, "hats": 4, "drive": 0.8,
              "desc": "напряжение, для проблемы в начале ролика"},
}


def note(semitones: float, root: float) -> float:
    return root * (2 ** (semitones / 12))


def env(i: int, n: int, attack: float, release: float) -> float:
    """Огибающая ноты. Без неё синтез щёлкает на стыках."""
    a = max(int(n * attack), 1)
    r = max(int(n * release), 1)
    if i < a:
        return i / a
    if i > n - r:
        return max((n - i) / r, 0.0)
    return 1.0


def kick(n: int) -> list[float]:
    """Бочка: частота падает с 120 до 45 Гц — так она читается на телефоне."""
    out = []
    for i in range(n):
        p = i / n
        f = 120 * (1 - p) ** 3 + 45
        out.append(math.sin(2 * math.pi * f * i / SR) * (1 - p) ** 2.2)
    return out


def snare(n: int, rng: random.Random) -> list[float]:
    out = []
    for i in range(n):
        p = i / n
        tone = math.sin(2 * math.pi * 190 * i / SR) * 0.35
        noise = rng.uniform(-1, 1) * 0.65
        out.append((tone + noise) * (1 - p) ** 3)
    return out


def hat(n: int, rng: random.Random) -> list[float]:
    return [rng.uniform(-1, 1) * (1 - i / n) ** 7 * 0.5 for i in range(n)]


def synth(freq: float, n: int, kind: str, level: float) -> list[float]:
    out = []
    for i in range(n):
        t = i / SR
        if kind == "bass":
            # синус с лёгкой второй гармоникой — читается на телефонном динамике
            v = math.sin(2 * math.pi * freq * t) * 0.8 + math.sin(4 * math.pi * freq * t) * 0.2
        else:
            # треугольник мягче пилы и не режет ухо на верхах
            x = (freq * t) % 1.0
            v = 4 * abs(x - 0.5) - 1
        out.append(v * env(i, n, 0.02, 0.35) * level)
    return out


def build(sec: float, mood: str, bpm: int | None, seed: int | None) -> list[float]:
    cfg = MOODS.get(mood, MOODS["energetic"])
    rng = random.Random(seed)
    bpm = bpm or cfg["bpm"]
    beat = 60.0 / bpm
    total = int(sec * SR)
    buf = [0.0] * total

    def mix(src: list[float], at: int, gain: float = 1.0) -> None:
        for i, v in enumerate(src):
            j = at + i
            if 0 <= j < total:
                buf[j] += v * gain

    scale = cfg["scale"]
    root = cfg["root"]
    # четыре аккорда по восемь долей — прогрессия, которая никому не надоедает
    chords = [0, -4, 3, -2]
    bars = int(sec / (beat * 4)) + 1

    kick_pos: list[int] = []

    for bar in range(bars):
        bar_at = int(bar * beat * 4 * SR)
        chord = chords[bar % len(chords)]
        # первые два такта — только ритм: интро без баса звучит собраннее
        intro = bar < 1

        for b in range(4):
            at = bar_at + int(b * beat * SR)

            if cfg["drive"] > 0.75 or b in (0, 2):
                mix(kick(int(0.14 * SR)), at, 0.9)
                kick_pos.append(at)

            if b in (1, 3):
                mix(snare(int(0.13 * SR), rng), at, 0.42 * cfg["drive"])

            for h in range(cfg["hats"]):
                mix(hat(int(0.05 * SR), rng), at + int(h * beat * SR / cfg["hats"]),
                    0.18 if h % 2 == 0 else 0.11)

            if not intro:
                bass_n = int(beat * SR * 0.92)
                mix(synth(note(chord + scale[0] - 12, root), bass_n, "bass", 0.55), at)

            if not intro and bar % 2 == 1:
                step = scale[(bar + b) % len(scale)]
                arp_n = int(beat * SR * 0.5)
                mix(synth(note(chord + step + 12, root), arp_n, "arp", 0.17), at)
                mix(synth(note(chord + step + 24, root), arp_n, "arp", 0.07),
                    at + int(beat * SR * 0.5))

    # сайдчейн: под каждой бочкой всё остальное на мгновение проседает —
    # именно это делает трек «живым», а не плоским ковром
    duck_len = int(0.11 * SR)
    for at in kick_pos:
        for i in range(duck_len):
            j = at + i
            if 0 <= j < total:
                buf[j] *= 0.45 + 0.55 * (i / duck_len)

    # затухание в конце, чтобы трек не обрывался на ролике
    fade = int(min(1.2, sec * 0.15) * SR)
    for i in range(fade):
        buf[total - 1 - i] *= i / fade
    rise = int(0.25 * SR)
    for i in range(rise):
        buf[i] *= i / rise

    peak = max((abs(v) for v in buf), default=1.0) or 1.0
    return [v / peak * 0.82 for v in buf]


def write_wav(samples: list[float], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32000)) for v in samples))


def to_mp3(src: Path, dst: Path) -> bool:
    ff = shutil.which("ffmpeg")
    if not ff:
        return False
    r = subprocess.run(
        [ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
         "-c:a", "libmp3lame", "-b:a", "192k", str(dst)],
        capture_output=True,
    )
    return r.returncode == 0


def musicgen(sec: float, prompt: str, out: Path) -> bool:
    """Нейросетевой движок. Работает, только если audiocraft уже установлен."""
    try:
        from audiocraft.models import MusicGen  # type: ignore
        from audiocraft.data.audio import audio_write  # type: ignore
    except ImportError:
        print("audiocraft не установлен — беру синтез. Установка: pip install audiocraft")
        return False

    model = MusicGen.get_pretrained("facebook/musicgen-small")
    model.set_generation_params(duration=min(sec, 30))
    wav = model.generate([prompt])
    audio_write(str(out.with_suffix("")), wav[0].cpu(), model.sample_rate, strategy="loudness")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="музыка под ролик")
    ap.add_argument("--sec", type=float, default=30.0)
    ap.add_argument("--mood", default="energetic", choices=list(MOODS))
    ap.add_argument("--bpm", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--engine", choices=["synth", "musicgen"], default="synth")
    ap.add_argument("--prompt", default="", help="описание для musicgen")
    ap.add_argument("--out", help="выходной файл .mp3 или .wav")
    ap.add_argument("--bank", type=int, help="сгенерировать столько треков разом")
    ap.add_argument("--out-dir", default="library")
    args = ap.parse_args()

    if args.bank:
        d = Path(args.out_dir)
        moods = list(MOODS)
        print(f"собираю банк из {args.bank} треков в {d}:")
        for i in range(args.bank):
            mood = moods[i % len(moods)]
            wav = d / f"{mood}-{i + 1:02d}.wav"
            write_wav(build(args.sec, mood, None, i + 1), wav)
            mp3 = wav.with_suffix(".mp3")
            if to_mp3(wav, mp3):
                wav.unlink()
                print(f"  {mp3.name}  ({MOODS[mood]['desc']})")
            else:
                print(f"  {wav.name}")
        return 0

    if not args.out:
        print("нужен --out или --bank")
        return 1

    out = Path(args.out)

    if args.engine == "musicgen":
        prompt = args.prompt or f"{args.mood} background music for a short product video, no vocals"
        if musicgen(args.sec, prompt, out):
            print(f"готово: {out}")
            return 0

    samples = build(args.sec, args.mood, args.bpm, args.seed)
    if out.suffix.lower() == ".mp3":
        tmp = out.with_suffix(".wav")
        write_wav(samples, tmp)
        if to_mp3(tmp, out):
            tmp.unlink()
        else:
            print("ffmpeg не найден — оставляю wav")
            out = tmp
    else:
        write_wav(samples, out)

    print(f"готово: {out}  ({args.mood}, {args.bpm or MOODS[args.mood]['bpm']} bpm, {args.sec:.0f} сек)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
