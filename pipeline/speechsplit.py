"""
Оставить в видео только речь автора, вырезав закадровую подсказку.

Живой креатор снимает так: звучит подсказка (суфлёр, диктор, запись
в динамике), он её слушает и повторяет вслух. В дорожку попадают оба
голоса, чередуясь: подсказка — повтор — подсказка — повтор.

    python speechsplit.py raw.mp4 --check              есть ли второй голос
    python speechsplit.py raw.mp4 --edl runs/edl.json  план нарезки
    python speechsplit.py raw.mp4 --out clean.mp4      чистовик
    python speechsplit.py raw.mp4 --out c.mp4 --verify контроль после сборки

Порядок ровно такой и другим быть не может:

  1. разделить дорожку на куски речи
  2. разложить куски на два уровня громкости — это и есть два говорящих
  3. автор — громкий: он говорит в микрофон, подсказка идёт из динамика
  4. уточнить правый край каждого куска по тишине
  5. выбросить фальстарты
  6. нарезать с микрофейдами
  7. проверить: в результате должен остаться ОДИН уровень

Четыре ошибки, каждая оставляет диктора в ролике. Все четыре были сделаны
на живом материале, прежде чем метод устоялся.

**Резать по тишине вместо разделения голосов.** Пауза не знает, кто говорит:
для неё подсказка и автор одинаково «звук». Убирая тишину, склеиваешь их.

**Верить правой границе куска.** Хвост куска затягивает паузу и прихватывает
начало следующей реплики — диктора. Правый край всегда уточнять по тишине.

**Брать порог тишины наугад.** Порог должен лежать **между** уровнями: выше
подсказки, ниже автора. Взял −50 дБ — подсказка считается звуком и остаётся;
взял −20 дБ — срезаются тихие окончания слов автора.

**Судить по высоте голоса.** Подсказку часто пишет сам автор или похожий
голос: на живом материале тон отличался всего на 17 Гц, и проверка по тону
сказала «один человек», хотя голосов было два. Тон — признак
вспомогательный, решает громкость.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

SR = 16000
WIN = 0.05           # шаг анализа
FLOOR_DB = -50.0     # ниже этого — тишина, а не речь
# Сшивка провалов внутри фразы. Величина зажата с двух сторон: больше —
# подсказка слипается с ответом в один кусок и повтор остаётся внутри него,
# меньше — фраза рассыпается на слоги. 0.12 подобрано на живом материале.
GAP_FILL = 0.12
MIN_SEG = 0.25       # кусок короче — щелчок или вдох
PAD_LEFT = 0.10      # не срезать первый звук
PAD_RIGHT = 0.18     # дать фразе дозвучать
FADE = 0.015         # микрофейд на стыке, иначе щелчки
MIN_GAP_DB = 4.0     # меньше — считаем, что второго голоса нет


def duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def audio(path: Path) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
             "-ac", "1", "-ar", str(SR), str(wav)], check=True)
        with wave.open(str(wav), "rb") as w:
            raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def db_map(sig: np.ndarray) -> np.ndarray:
    step = int(SR * WIN)
    n = len(sig) // step
    db = np.full(n, -99.0, dtype=np.float32)
    for i in range(n):
        f = sig[i * step:(i + 1) * step]
        if f.size:
            rms = float(np.sqrt(np.mean(f ** 2)))
            if rms > 1e-8:
                db[i] = 20 * np.log10(rms)
    return db


def rms_db(sig: np.ndarray, a: float, b: float) -> float:
    f = sig[int(a * SR):int(b * SR)]
    if f.size < SR // 20:
        return -99.0
    rms = float(np.sqrt(np.mean(f ** 2)))
    return 20 * np.log10(rms) if rms > 1e-8 else -99.0


def speech_chunks(sig: np.ndarray) -> list[tuple[float, float, float]]:
    """Куски речи и громкость каждого. Провалы сшиваются коротко, чтобы
    подсказка и ответ на неё не слиплись в один кусок."""
    db = db_map(sig)
    on = db > FLOOR_DB

    fill = int(GAP_FILL / WIN)
    i = 0
    while i < len(on):
        if not on[i]:
            j = i
            while j < len(on) and not on[j]:
                j += 1
            if 0 < i and j < len(on) and (j - i) <= fill:
                on[i:j] = True
            i = j
        else:
            i += 1

    out: list[tuple[float, float, float]] = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and on[j]:
                j += 1
            a, b = i * WIN, j * WIN
            if b - a >= MIN_SEG:
                out.append((a, b, rms_db(sig, a, b)))
            i = j
        else:
            i += 1
    return out


def split_levels(levels: np.ndarray) -> tuple[float, float, float] | None:
    """
    Порог между двумя уровнями громкости — методом Оцу.

    Порог берётся из самих данных, а не назначается: у разных съёмок
    расстояние между голосами разное, а промах в пару децибел оставляет
    подсказку в ролике.
    """
    if levels.size < 4:
        return None
    best, thr = -1.0, None
    for t in np.arange(levels.min() + 1, levels.max() - 1, 0.25):
        lo, hi = levels[levels < t], levels[levels >= t]
        if lo.size < 2 or hi.size < 2:
            continue
        var = lo.size * hi.size * (lo.mean() - hi.mean()) ** 2
        if var > best:
            best, thr = var, float(t)
    if thr is None:
        return None
    lo, hi = levels[levels < thr], levels[levels >= thr]
    return thr, float(lo.mean()), float(hi.mean())


def report(chunks: list[tuple[float, float, float]]) -> dict:
    levels = np.array([c[2] for c in chunks])
    split = split_levels(levels)
    if split is None:
        return {"есть": False, "почему": "речи слишком мало, чтобы судить"}
    thr, quiet, loud = split
    gap = loud - quiet
    есть = gap >= MIN_GAP_DB
    return {
        "есть": bool(есть),
        "порог дБ": round(thr, 1),
        "подсказка дБ": round(quiet, 1),
        "автор дБ": round(loud, 1),
        "разрыв дБ": round(gap, 1),
        "кусков тихих": int((levels < thr).sum()),
        "кусков громких": int((levels >= thr).sum()),
        "почему": (f"два уровня громкости с разрывом {gap:.1f} дБ — "
                   "тихий это подсказка"
                   if есть else
                   f"уровень один (разрыв всего {gap:.1f} дБ) — второго голоса нет"),
    }


SMOOTH = 0.30      # окно сглаживания: короче — ловит провалы внутри слов
TAIL_MAX = 0.30    # насколько продлевать фразу за границу громкого участка
MIN_ISLAND = 0.45  # громкий островок короче — всплеск диктора, не фраза автора
PROMPT_DIP = 0.50  # провал длиннее этого и на уровне голоса — реплика диктора
BREATH_DB = -48.0  # тише этого — дыхание и тишина, громче — чей-то голос


def _runs(mask: np.ndarray, val: bool) -> list[tuple[int, int]]:
    out, k = [], 0
    while k < len(mask):
        if bool(mask[k]) == val:
            j = k
            while j < len(mask) and bool(mask[j]) == val:
                j += 1
            out.append((k, j))
            k = j
        else:
            k += 1
    return out


def author_regions(db: np.ndarray, a: float, b: float, thr: float) -> list[tuple[float, float]]:
    """
    Где внутри куска действительно говорит автор.

    Возвращает **список** участков, а не пару границ: подсказка может
    оказаться в середине куска, между двумя фразами автора. Так и уехал
    диктор в готовый ролик — обрезались только края, а тихая вставка
    посередине оставалась нетронутой.

    Порядок разбора важен, и он выведен из брака:

    1. **Сначала гасятся громкие островки короче MIN_ISLAND** — это
       ударные слова самого диктора, пробившиеся через порог. Если гасить
       их после классификации провалов, островок разрывает реплику диктора
       на два коротких провала, каждый из которых сходит за дыхание.
    2. **Провал — дыхание или диктор — решается по двум признакам сразу.**
       Только по уровню нельзя: тихие окончания слов автора живут на уровне
       диктора, и фраза рассыпается. Только по длине нельзя: реплика диктора
       с тихим заходом неотличима от вдоха. Диктор — это провал длиннее
       PROMPT_DIP **и** на уровне голоса (медиана громче BREATH_DB).
    3. **Хвосты фраз ведутся по затуханию, а не по порогу.** Порог
       отсекает последний согласный, и слово обрывается за миллисекунды
       до конца. Но в сторону диктора хвост не продлевается: затухание
       должно идти вниз, ровный уровень — это уже чужая речь.
    """
    win = max(1, int(SMOOTH / WIN))
    i0, i1 = int(a / WIN), min(int(b / WIN), len(db))
    n = i1 - i0
    if n <= win:
        return [(a, b)]

    loud = np.zeros(n, dtype=bool)
    for k in range(n - win + 1):
        if float(np.mean(db[i0 + k:i0 + k + win])) >= thr:
            loud[k:k + win] = True
    if not loud.any():
        return []

    def dictorish(k: int, j: int) -> bool:
        """Провал похож на реплику диктора: тихий голос почти без громких окон."""
        dip = db[i0 + k:i0 + j]
        return (float(np.median(dip)) >= BREATH_DB
                and float(np.mean(dip >= thr)) < 0.25)

    # 1. всплески диктора. Громкое ударное слово диктора неотличимо от слова
    #    автора по уровню — на живом материале оба дали −24 дБ. Различает их
    #    окружение: всплеск диктора сидит между двумя дикторскими провалами,
    #    а короткий кусок автора граничит со своей же речью или с тишиной.
    #    Островок у края куска не трогаем: короткий кусок целиком — это
    #    короткая фраза автора («Կհանդիպենք»), а не всплеск.
    # Сосед-провал должен быть весомым: провал в одно-два окна — это
    # мгновенный спад внутри слова, по нему судить нельзя. Из-за такого
    # микропровала под нож ушёл конец слова самого автора.
    weighty = int(0.20 / WIN)
    for k, j in _runs(loud, True):
        if not (0 < k and j < n and (j - k) * WIN < MIN_ISLAND):
            continue
        left = next(((x, y) for x, y in _runs(loud, False) if y == k), None)
        right = next(((x, y) for x, y in _runs(loud, False) if x == j), None)
        if (left and right
                and left[1] - left[0] >= weighty and dictorish(*left)
                and right[1] - right[0] >= weighty and dictorish(*right)):
            loud[k:j] = False
    if not loud.any():
        return []

    # 2. провалы: дыхание сшиваем, диктора оставляем разрезом.
    #    Провал внутри живой речи набирает громкие окна из-за размытия
    #    скользящим средним — сшиваем его, иначе хвост слова уйдёт под нож.
    for k, j in _runs(loud, False):
        if k == 0 or j == n:
            continue
        if (j - k) * WIN >= PROMPT_DIP and dictorish(k, j):
            continue
        loud[k:j] = True

    # 3. границы: к тишине — с запасом, к диктору — по затуханию
    regions = _runs(loud, True)
    out: list[tuple[float, float]] = []
    for k, j in regions:
        if k == 0:
            sa = max(0.0, a - PAD_LEFT)
        else:
            sa = attack_back(db, (i0 + k) * WIN, thr)
        if j == n:
            sb = tail_fwd(db, (i0 + j) * WIN, thr) + PAD_RIGHT
        else:
            sb = tail_fwd(db, (i0 + j) * WIN, thr)
        if sb - sa >= MIN_SEG:
            out.append((sa, sb))
    return out


def tail_fwd(db: np.ndarray, t: float, thr: float) -> float:
    """
    Хвост слова за границей громкого участка.

    Идём вперёд, пока звук затухает: каждый шаг не громче предыдущего
    (с малым допуском). Подъём уровня — уже чужая реплика, стоп. Так хвост
    последнего согласного остаётся в кадре, а заход диктора — нет.
    """
    i = int(t / WIN)
    end = min(i + int(TAIL_MAX / WIN), len(db))
    prev = db[i - 1] if i > 0 else thr
    last = i
    while i < end:
        if db[i] < BREATH_DB:
            break                       # дозвучало до тишины
        # Допуск 3 дБ: хвост фрикативных дребезжит на пару децибел вверх-вниз,
        # и жёсткая проверка обрывала его. Чёткий подъём — чужая реплика.
        if db[i] > prev + 3.0:
            break
        prev = db[i]
        i += 1
        last = i
    return last * WIN


def attack_back(db: np.ndarray, t: float, thr: float) -> float:
    """То же назад: атака первого звука начинается тише порога."""
    first = int(t / WIN)
    i = first - 1
    stop = max(0, first - int(TAIL_MAX / WIN))
    prev = db[first] if first < len(db) else thr
    while i >= stop:
        if db[i] < BREATH_DB:
            break
        if db[i] > prev + 1.5:
            break
        prev = db[i]
        first = i
        i -= 1
    return first * WIN


def transcribe_chunks(src: Path, spans: list[tuple[float, float]], lang: str) -> list[str]:
    """Текст каждого куска — чтобы найти фальстарты."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        return [""] * len(spans)

    model = WhisperModel("small", device="cpu", compute_type="int8")
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for k, (a, b) in enumerate(spans):
            p = Path(tmp) / f"c{k}.wav"
            subprocess.run(
                [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", str(src),
                 "-ac", "1", "-ar", "16000", str(p)], check=True)
            segs, _ = model.transcribe(str(p), language=lang, vad_filter=False,
                                       condition_on_previous_text=False)
            out.append(" ".join(s.text.strip() for s in segs))
    return out


def drop_repeats(texts: list[str], same: float = 0.55) -> list[int]:
    """
    Индексы кусков, которые надо выбросить как повторы.

    Два случая дают одинаковую картину — пару соседних кусков с одним
    текстом:

    * подсказка прозвучала, автор повторил за ней;
    * автор сбился на середине и сказал фразу заново.

    В обоих **нужен второй**: автор повторяет за подсказкой, а после
    фальстарта говорит целиком. Поэтому правило одно — из пары
    выбрасываем первый.

    Сравнение нечёткое: распознавание армянского пишет одну и ту же фразу
    по-разному («որոսում երականչուր անհատ» и «Մորտսում իրը կանչուր անհատ»),
    и сверка по первым буквам такую пару не ловит.
    """
    import difflib

    norm = lambda t: re.sub(r"[^\w ]", "", t.lower()).strip()
    bad: list[int] = []
    for i in range(len(texts) - 1):
        a, b = norm(texts[i]), norm(texts[i + 1])
        if len(a) < 5 or len(b) < 5:
            continue
        # сравниваем по общей длине: короткий обрывок против полной фразы
        n = min(len(a), len(b))
        if difflib.SequenceMatcher(None, a[:n], b[:n]).ratio() >= same:
            bad.append(i)
    return bad


def cut(src: Path, spans: list[tuple[float, float]], out: Path) -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for k, (a, b) in enumerate(spans):
            p = Path(tmp) / f"p{k:03d}.mp4"
            d = b - a
            af = (f"afade=t=in:st=0:d={FADE},"
                  f"afade=t=out:st={max(0.0, d - FADE):.3f}:d={FADE}")
            r = subprocess.run(
                [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
                 "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(src),
                 "-af", af,
                 "-c:v", "libx264", "-preset", "fast", "-crf", "16",
                 "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                 "-avoid_negative_ts", "make_zero", str(p)],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode != 0:
                sys.stderr.write((r.stderr or "")[-500:])
                return False
            parts.append(p)

        lst = Path(tmp) / "list.txt"
        lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
             "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c:v", "libx264", "-preset", "medium", "-crf", "17",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            sys.stderr.write((r.stderr or "")[-500:])
            return False
    return True


def verify(path: Path) -> bool:
    """В чистовике должен остаться один уровень громкости."""
    rep = report(speech_chunks(audio(path)))
    if rep["есть"]:
        print(f"  ОСТАЛСЯ ЛИШНИЙ ГОЛОС: {rep['почему']}")
        print(f"  тихих кусков {rep['кусков тихих']}, громких {rep['кусков громких']}")
        return False
    print(f"  чисто: {rep['почему']}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="убрать закадровую подсказку")
    ap.add_argument("src")
    ap.add_argument("--edl", help="куда записать план нарезки")
    ap.add_argument("--out", help="куда собрать чистовик")
    ap.add_argument("--check", action="store_true", help="только проверить и выйти")
    ap.add_argument("--verify", action="store_true", help="проверить готовый файл")
    ap.add_argument("--lang", default="hy")
    ap.add_argument("--keep-false-starts", action="store_true",
                    help="не выбрасывать фальстарты")
    ap.add_argument("--force", action="store_true",
                    help="резать, даже если второго голоса не видно")
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"нет файла: {src}")
        return 1

    if args.verify:
        return 0 if verify(src) else 1

    sig = audio(src)
    chunks = speech_chunks(sig)
    if not chunks:
        print("речь не найдена")
        return 1

    rep = report(chunks)
    if args.check:
        for k, v in rep.items():
            print(f"  {k}: {v}")
        return 0

    if not rep["есть"] and not args.force:
        print(f"второго голоса не видно: {rep['почему']}")
        print("файл не тронут. Резать всё равно — флаг --force")
        return 0

    thr = rep["порог дБ"]
    total = duration(src)

    # автор — громкий: он говорит в микрофон, подсказка идёт из динамика
    mine = [(a, b) for a, b, lv in chunks if lv >= thr]
    print(f"порог {thr} дБ · подсказка {rep['подсказка дБ']} дБ · "
          f"автор {rep['автор дБ']} дБ · разрыв {rep['разрыв дБ']} дБ")
    print(f"кусков всего {len(chunks)}, из них автора {len(mine)}")

    # Внутри куска подсказка может сидеть между двумя фразами автора —
    # вырезаем каждый громкий участок отдельно, а не только края.
    # Отступы к тишине и хвосты по затуханию считает сам author_regions.
    db = db_map(sig)
    spans = []
    for a, b in mine:
        for sa, sb in author_regions(db, a, b, thr):
            spans.append((max(0.0, sa), min(total, sb)))

    texts: list[str] = []
    if not args.keep_false_starts:
        print("слушаю куски, ищу повторы…")
        texts = transcribe_chunks(src, spans, args.lang)
        bad = set(drop_repeats(texts))
        # хвост записи: короткая реплика не по тексту («ладно», «ну всё»)
        if texts and len(re.sub(r"[^\w ]", "", texts[-1]).strip()) < 12:
            bad.add(len(texts) - 1)
        if bad:
            for i in sorted(bad):
                print(f"  выброшено: {spans[i][0]:6.2f}–{spans[i][1]:6.2f}  {texts[i][:42]}")
            spans = [s for i, s in enumerate(spans) if i not in bad]
            texts = [t for i, t in enumerate(texts) if i not in bad]

    kept = sum(b - a for a, b in spans)
    print(f"\nисходник {total:.1f} с → речь автора {kept:.1f} с "
          f"({len(spans)} фрагментов), убрано {total - kept:.1f} с")
    for i, (a, b) in enumerate(spans, 1):
        t = f"  {texts[i-1][:40]}" if texts else ""
        print(f"  {i:2d}. {a:6.2f} → {b:6.2f}   {b - a:5.2f} с{t}")

    if args.edl:
        Path(args.edl).parent.mkdir(parents=True, exist_ok=True)
        Path(args.edl).write_text(json.dumps(
            [{"start": round(a, 2), "end": round(b, 2),
              "text": texts[i] if texts else ""} for i, (a, b) in enumerate(spans)],
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"план: {args.edl}")

    if args.out:
        if not cut(src, spans, Path(args.out)):
            return 1
        print(f"чистовик: {args.out}  ({duration(Path(args.out)):.1f} с)")
        print("контроль:")
        if not verify(Path(args.out)):
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
