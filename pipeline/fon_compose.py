#!/usr/bin/env python3
"""
Подстановка фона под готовый слой человека — без повторной вырезки.

matte.py один раз вырезает человека (--fg-out слой, --alpha-out маска). Дальше фон
меняется за минуты: так работают в профессиональном монтаже — ключ отдельно, фон
отдельно. Здесь же то, что прячет вырезку от глаза:

  свет фона на кромке (light wrap);
  фон в расфокусе и по яркости/теплоте под человека;
  одинаковое зерно на фоне и на человеке — чистый размытый фон за шумной съёмкой
  с телефона читается как наклейка;
  лёгкое затемнение краёв кадра — взгляд идёт к лицу;
  снятие зелёного отлива (--despill), если снято на зелёном фоне.

  python fon_compose.py --video chistovik.mp4 --alpha alpha.mkv --plate-cache plate.npz --bg fon.mp4 --out talk.mp4
  python fon_compose.py ... --still 5.0 --out proba.png          # один кадр для сравнения фонов

С --video край пересобирается здесь же: подрезка маски и цвет края по подложке стены.
Нейросеть второй раз не нужна — правка кромки занимает минуты, а не двадцать.

Длинный ролик в разрешении исходника собирается кусками одновременно (--workers,
17.09.2026). numpy считает кадр одним потоком: один процесс на 4K занимал одно ядро
из восемнадцати — 4 с на кадр, полтора часа на 40 секунд ролика. Куски — те же кадры
тем же кодом: фон идёт по общему счёту кадров ролика, подложка стены перед каждым
куском разгоняется на RAZGON кадров, куски склеиваются без перекодирования. Сколько
кусков — решают ядра, выданные очередью, и свободная память; --workers 1 — как раньше.
"""
if __name__ == "__main__":  # М-44: мимо очереди тяжёлое не идёт — перезапуск через неё
    import ochered
    ochered.v_ocheredi()
import argparse, ctypes, json, os, shutil, subprocess, sys, time
from pathlib import Path
import numpy as np
import cv2
if hasattr(sys.stdout, "reconfigure"):  # консоль cp1251 роняла вывод со знаками «→», «×», «≈»
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matte_core import probe, reader, read_frame, Background, PlateTracker, foreground_colors, choke, repair_holes

RAZGON = 30          # кадров разгона подложки перед куском: сглаживание 0.85 за 30 кадров забывает старт
GB_NA_MP = 0.30      # ГБ памяти на мегапиксель кадра у одного куска с его тремя ffmpeg (4K — 2.5 ГБ).
                     # Замеры 17.09.2026, видео 10 в 4K: пять кусков упёрлись в предел фиксации Windows
                     # при 3.4 ГБ свободной RAM — считать надо фиксацию; четыре куска при 12.4 ГБ
                     # свободных прошли, заняв около 10 ГБ: 1.45 с/кадр против 3.75 одним процессом.
ZAPAS_GB = 2.0       # сколько памяти не трогать: рядом живут ферма и чаты
KUSKOV_MAKS = 9

p = argparse.ArgumentParser()
src = p.add_mutually_exclusive_group(required=True)
src.add_argument("--video", help="чистовик, по которому считалась маска (со звуком): край пересобирается")
src.add_argument("--fg", help="готовый слой человека из matte.py --fg-out (цвет, умноженный на маску)")
p.add_argument("--plate-cache", default="", help="подложка стены из matte.py: точнее цвет края")
p.add_argument("--choke", type=int, default=1, help="подрезать маску внутрь, px (только с --video)")
p.add_argument("--edge-soft", type=float, default=0.6, help="мягкость кромки, px (только с --video)")
p.add_argument("--alpha", required=True, help="маска из matte.py --alpha-out")
p.add_argument("--bg", required=True, help="картинка или видео фона")
p.add_argument("--out", required=True)
p.add_argument("--from", dest="t0", type=float, default=None)
p.add_argument("--to", dest="t1", type=float, default=None)
p.add_argument("--still", type=float, default=None, help="собрать один кадр на этой секунде (PNG)")
p.add_argument("--workers", type=int, default=0,
               help="сколько кусков собирать одновременно: 0 — решить по ядрам и памяти, 1 — одним процессом")
p.add_argument("--kusok", default="", help=argparse.SUPPRESS)  # служебное: "с кадра,до кадра,кадров фона,сдвиг фона"
# фон
p.add_argument("--bg-from", type=float, default=0.0, help="с какой секунды фона начинать")
p.add_argument("--bg-blur", type=float, default=10.0, help="расфокус фона, sigma px (0 — резкий)")
p.add_argument("--bg-slow", type=float, default=1.0)
p.add_argument("--bg-zoom", type=float, default=1.0)
p.add_argument("--bg-dx", type=int, default=0)
p.add_argument("--bg-push", type=float, default=0.04)
p.add_argument("--bg-bright", type=float, default=1.0, help="яркость фона")
p.add_argument("--bg-warm", type=float, default=0.0, help="-1..1: холоднее / теплее")
p.add_argument("--bg-sat", type=float, default=1.0, help="насыщенность фона")
p.add_argument("--vignette", type=float, default=0.25, help="0..1 затемнение краёв кадра")
# человек
p.add_argument("--exposure", type=float, default=1.0)
p.add_argument("--grade", default="1.0,1.0,1.0")
p.add_argument("--head", default="", help="x,y,w,h лица: центр света для --relight")
p.add_argument("--relight", type=float, default=0.0)
p.add_argument("--lightwrap", type=float, default=0.25)
p.add_argument("--despill", type=float, default=0.0,
               help="0..1 снятие зелёного отлива с человека — только для съёмки на зелёном фоне (М-12)")
p.add_argument("--grain", type=float, default=0.012, help="зерно на весь кадр, СКО в долях яркости")
p.add_argument("--quiet", action="store_true")
a = p.parse_args()


def log(*x):
    if not a.quiet:
        print(*x, flush=True)


SRC = a.video or a.fg
W, H, FPS, dur = probe(SRC)
t0 = a.still if a.still is not None else (a.t0 or 0.0)
t1 = t0 + 1.0 / FPS if a.still is not None else (min(a.t1, dur) if a.t1 else dur)
N = max(1, int(round((t1 - t0) * FPS)))


def _kadrov(path) -> int:
    """Сколько кадров в видеодорожке на самом деле: пакеты считаются без декодирования."""
    try:
        out = subprocess.check_output(
            f'ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets '
            f'-of csv=p=0 "{path}"', shell=True, text=True)
        return int(out.strip().split(",")[0])
    except Exception:
        return 0


# Длительность файла считается со звуком, а видеодорожка бывает короче на кадр-два.
# Видео 10 (18.09.2026): N вышло 1280 при 1279 кадрах — последний кусок собрал все свои
# 319, вышел с кодом 1 «не хватило кадра», и сборка 20 минут пересобирала его зря, а потом
# упала. Кадров в ролике столько, сколько их есть в видео и в маске.
if a.still is None and not a.kusok:
    _est = [x for x in (_kadrov(SRC), _kadrov(a.alpha)) if x > 0]
    if _est:
        N = max(1, min(N, min(_est) - int(round(t0 * FPS))))
# фон: для кадра-пробы начинаем с той же секунды фона, что и в ролике
bg_start = a.bg_from + (t0 if a.still is not None or a.t0 else 0.0)
BG_SDVIG = int(bg_start * FPS)


# ------------------------------------------------------------------ куски

def _svobodno_gb() -> float:
    """Меньшее из свободной RAM и свободной фиксации (commit): кончается фиксация —
    память не выделяется никому, и ферме тоже, хотя RAM ещё есть."""
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (k, ctypes.c_ulonglong) for k in ("total", "avail", "tpf", "apf", "tv", "av", "aev")]
    try:
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return min(m.avail, m.apf) / 2 ** 30
    except Exception:
        return 0.0


def _potoki() -> int:
    """Сколько потоков у этой работы: очередь пишет это в OMP_NUM_THREADS."""
    v = os.environ.get("OMP_NUM_THREADS", "") if os.environ.get("REELS_OCHERED") else ""
    return int(v) if v.isdigit() and int(v) > 0 else (os.cpu_count() or 2)


def skolko_kuskov() -> int:
    if a.still is not None or a.kusok:
        return 1
    if a.workers > 0:
        return max(1, min(a.workers, N // 30 or 1))
    if N < 240 or W * H < 3_000_000:      # короткое и 1080p быстрее одним процессом
        return 1
    po_pamyati = int((_svobodno_gb() - ZAPAS_GB) / (GB_NA_MP * W * H / 1e6))
    return max(1, min(_potoki() // 2, po_pamyati, KUSKOV_MAKS, N // 60))


def sobrat_kuskami(k: int) -> int:
    """Раздать ролик k процессам, дождаться, склеить без перекодирования, подложить звук."""
    started = time.time()
    papka = Path(a.out).with_name(Path(a.out).stem + ".kuski")
    shutil.rmtree(papka, ignore_errors=True)
    papka.mkdir(parents=True)
    granicy = [round(i * N / k) for i in range(k + 1)]
    na_kusok = max(1, _potoki() // k)
    env = dict(os.environ, REELS_FON_POTOKI=str(na_kusok))
    log(f"сборка кусками: {k} одновременно по {na_kusok} потока, {N} кадров {W}x{H}, "
        f"свободной памяти {_svobodno_gb():.1f} ГБ")
    kuski = [papka / f"kusok_{i:02d}.mp4" for i in range(k)]

    def pusk(i: int) -> tuple:
        argv = [sys.executable, str(Path(__file__).resolve())] + sys.argv[1:] + [
            "--out", str(kuski[i]), "--workers", "1", "--quiet",
            "--kusok", f"{granicy[i]},{granicy[i + 1]},{N + BG_SDVIG},{BG_SDVIG}"]
        zhurnal = open(papka / f"kusok_{i:02d}.log", "a", encoding="utf-8")
        return subprocess.Popen(argv, env=env, stdout=zhurnal, stderr=subprocess.STDOUT), zhurnal

    def gotovo_kadrov() -> int:
        vsego = 0
        for kus in kuski:
            try:
                vsego += int(kus.with_suffix(".n").read_text() or 0)
            except (OSError, ValueError):
                pass
        return vsego

    def zhdat(raboty: list) -> None:
        poslednij = time.time()
        while any(r.poll() is None for r, _ in raboty):
            time.sleep(2)
            if time.time() - poslednij >= 30:
                poslednij, g, el = time.time(), gotovo_kadrov(), time.time() - started
                if g:
                    log(f"  кадр {g}/{N}  {el / g:.2f} с/кадр на весь ролик, осталось ≈{(N - g) * el / g / 60:.0f} мин")
        for _, zh in raboty:
            zh.close()

    raboty = []
    for i in range(k):
        raboty.append(pusk(i))
        time.sleep(1.5)  # не все разом: на старте у каждого куска всплеск памяти
    zhdat(raboty)
    # Упавший кусок (обычно не хватило памяти, пока шли все разом) пересобирается один.
    upali = [i for i, (r, _) in enumerate(raboty) if r.returncode != 0]
    for i in upali:
        log(f"  кусок {i} не собрался (код {raboty[i][0].returncode}) — пересобираю его отдельно")
        kuski[i].with_suffix(".n").unlink(missing_ok=True)
        raboty[i] = pusk(i)
        zhdat([raboty[i]])
        if raboty[i][0].returncode != 0:
            hvost = (papka / f"kusok_{i:02d}.log").read_text(encoding="utf-8", errors="replace")[-1500:]
            print(f"кусок {i} не собрался и отдельно (код {raboty[i][0].returncode}); журналы — {papka}\n{hvost}",
                  file=sys.stderr, flush=True)
            return 1

    itogi = [json.loads(kus.with_suffix(".json").read_text(encoding="utf-8")) for kus in kuski]
    sdelano = sum(x["n"] for x in itogi)
    # Хвост короче расчётного на кадр-два при полных остальных кусках — видеодорожка
    # кончилась раньше, чем обещал счёт кадров; это конец ролика, а не поломка.
    hvost_korotkij = (0 < N - sdelano <= 2
                      and all(itogi[i]["n"] == granicy[i + 1] - granicy[i] for i in range(k - 1)))
    if sdelano != N and not hvost_korotkij:
        print(f"кадров собрано {sdelano}, а нужно {N}: {[x['n'] for x in itogi]}; журналы — {papka}",
              file=sys.stderr, flush=True)
        return 1
    if hvost_korotkij:
        log(f"  видеодорожка короче расчётного на {N - sdelano} кадр.: в ролике {sdelano} кадров")
    spisok = papka / "spisok.txt"
    spisok.write_text("".join(f"file '{kus.resolve().as_posix()}'\n" for kus in kuski), encoding="utf-8")
    ss_a = f"-ss {t0} " if t0 else ""
    to_a = f"-t {t1 - t0} " if a.t1 else ""
    kod = subprocess.call(
        f'ffmpeg -v error -f concat -safe 0 -i "{spisok}" {ss_a}{to_a}-i "{SRC}" -map 0:v -map 1:a? '
        f'-c:v copy -c:a aac -b:a 256k -shortest "{a.out}" -y', shell=True)
    if kod != 0:
        print(f"склейка кусков не удалась (код {kod}); куски — {papka}", file=sys.stderr, flush=True)
        return 1
    shutil.rmtree(papka, ignore_errors=True)
    if a.video and a.plate_cache:
        log(f"дыры в маске закрыты: {sum(x['frames_fixed'] for x in itogi)} кадров, "
            f"{sum(x['holes_fixed'] for x in itogi)} пикселей")
    el = time.time() - started
    log(f"готово: {sdelano} кадров за {el:.0f} с ({el / sdelano:.2f} с/кадр, кусков {k}) → {a.out}")
    return 0


if __name__ == "__main__":
    _k = skolko_kuskov()
    if _k > 1:
        sys.exit(sobrat_kuskami(_k))

# ------------------------------------------------------------------ один процесс: весь ролик, кадр или кусок

F0, F1, BG_N, BG_I = 0, N, N + BG_SDVIG, BG_SDVIG
if a.kusok:
    F0, F1, BG_N, BG_I = (int(x) for x in a.kusok.split(","))
    cv2.setNumThreads(max(1, int(os.environ.get("REELS_FON_POTOKI") or 2)))
N_KUSKA = F1 - F0

BG = Background(a.bg, W, H, BG_N, fps=FPS, blur=a.bg_blur, slow=a.bg_slow,
                zoom=a.bg_zoom, dx=a.bg_dx, push=a.bg_push, log=log)
BG.skip(BG_I + F0)

# цвет фона
M = np.eye(3, dtype=np.float32)
if a.bg_warm:
    k = 0.12 * a.bg_warm
    M = np.diag([1 + k, 1 + k * 0.25, 1 - k]).astype(np.float32)
lum_w = np.array([0.2126, 0.7152, 0.0722], np.float32)

yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
VIG = None
if a.vignette > 0:
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H * 0.42) / (H * 0.62)) ** 2)
    VIG = (1 - a.vignette * np.clip(r - 0.35, 0, 1) ** 1.6).astype(np.float32)[..., None]
    del r
LIGHT = None
if a.relight > 0:
    fy = float(a.head.split(",")[1]) if a.head else 0.35
    ramp = np.clip((yy[:, :1] - fy * H) / ((1.0 - fy) * H), 0, 1)
    LIGHT = (1.0 - a.relight * ramp ** 1.2)[..., None] * np.ones((1, W, 1), np.float32)
del yy, xx
gr = np.array([float(x) for x in a.grade.split(",")], np.float32).reshape(1, 1, 3) * a.exposure
rng = np.random.default_rng(7 + F0)

tracker = None
if a.video and a.plate_cache:
    z = np.load(a.plate_cache)
    tracker = PlateTracker({"plate": z["plate"], "seen": z["seen"], "conf": z["conf"], "q": int(z["q"])}, W, H)

# Кусок из середины ролика начинает читать раньше на разгон подложки и встаёт между
# кадрами: на полкадра раньше нужного — первым придёт ровно нужный кадр.
RAZGON_K = min(F0, RAZGON) if (a.kusok and tracker) else 0
if a.kusok and F0 - RAZGON_K > 0:
    ss = t0 + (F0 - RAZGON_K - 0.5) / FPS
else:
    ss = t0 if t0 else None
konec = None if a.kusok else (t1 if (a.t1 or a.still is not None) else None)
# У куска декодеры и кодировщик с потолком потоков: каждый поток ffmpeg на 4K держит
# свои кадры в памяти, а кусков несколько. Читать 4K со скоростью кадр в секунду хватит двух.
DEK = "-threads 2 " if a.kusok else ""
# Кусок встаёт по дробному -ss, поэтому читает кадры как в файле, без выравнивания частоты (М-53):
# иначе ffmpeg дублирует первый кадр, и кусок сдвигается на кадр против звука.
PASS = "-fps_mode passthrough " if a.kusok else ""
rf = reader(SRC, W, H, ss=ss, to=konec, threads=2 if a.kusok else None, passthrough=bool(a.kusok))
# Маска может быть меньше кадра: её считают в 1080p, а кадр собирают в разрешении
# исходника, чтобы наезд на крупность не мылил картинку (М-36). Край при этом
# пересобирается по полному кадру, растягивается только сама маска.
AW, AH = probe(a.alpha)[:2]
scale_alpha = f"-vf scale={W}:{H}:flags=bicubic " if (AW, AH) != (W, H) else ""
if scale_alpha:
    log(f"маска {AW}x{AH} растягивается под кадр {W}x{H}")
ra = subprocess.Popen(
    f'ffmpeg -v error {DEK}{"-ss " + str(ss) + " " if ss else ""}-i "{a.alpha}" '
    f'{"-t " + str(konec - t0) + " " if konec is not None else ""}{PASS}{scale_alpha}-f rawvideo -pix_fmt gray -',
    shell=True, stdout=subprocess.PIPE, bufsize=W * H * 4)

wr = None
if a.kusok:  # кусок — только картинка: звук подкладывается один раз при склейке
    wr = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - '
        f'-c:v libx264 -preset medium -crf 16 -threads 4 -x264-params rc-lookahead=20 -pix_fmt yuv420p "{a.out}" -y',
        shell=True, stdin=subprocess.PIPE)
elif a.still is None:
    ss_a = f"-ss {t0} " if t0 else ""
    to_a = f"-t {t1 - t0} " if a.t1 else ""
    wr = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {ss_a}{to_a}-i "{SRC}" '
        f'-map 0:v -map 1:a? -c:v libx264 -preset medium -crf 16 -pix_fmt yuv420p -c:a aac -b:a 256k -shortest "{a.out}" -y',
        shell=True, stdin=subprocess.PIPE)

started = time.time()
for _ in range(RAZGON_K):  # разгон: подложка привыкает к яркости камеры, кадры не пишутся
    fgp = read_frame(rf, W, H)
    raw = ra.stdout.read(W * H)
    if fgp is None or len(raw) < W * H:
        break
    tracker.frame(fgp, np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32) / 255.0)

n = 0
holes_fixed = frames_fixed = 0
while n < N_KUSKA:
    fgp = read_frame(rf, W, H)
    raw = ra.stdout.read(W * H)
    if fgp is None or len(raw) < W * H:
        break
    al = np.frombuffer(raw, np.uint8).reshape(H, W).astype(np.float32) / 255.0
    if a.video:
        # край из исходника: подрезка маски и очищенный от стены цвет
        I = fgp
        Bp = tracker.frame(I, al) if tracker else None
        if Bp is not None:
            al, fixed = repair_holes(I, al, Bp)
            holes_fixed += fixed
            frames_fixed += fixed > 200
        al = choke(al, a.choke, a.edge_soft)
        fgp = foreground_colors(I, al, plate=Bp) * al[..., None]
    if a.despill > 0:
        # Отлив зелёного полотна на коже, волосах и кромке: зелёный сверх среднего
        # красного и синего уходит, часть яркости возвращается. До 17.09.2026 это
        # было только в пробе matte.py, и на зелёной съёмке кромка в ролике зеленела.
        rb = (fgp[..., 0] + fgp[..., 2]) * 0.5
        exc = np.maximum(fgp[..., 1] - rb, 0.0) * a.despill
        fgp = np.stack([fgp[..., 0], fgp[..., 1] - exc, fgp[..., 2]], axis=-1) + (exc * 0.35)[..., None]
    bg = BG.next()
    if a.bg_warm:
        bg = bg @ M.T
    if a.bg_sat != 1.0:
        l = (bg @ lum_w)[..., None]
        bg = l + (bg - l) * a.bg_sat
    bg = np.clip(bg * a.bg_bright, 0, 1)
    if VIG is not None:
        bg = bg * VIG

    fgp = fgp * gr
    if LIGHT is not None:
        fgp = fgp * LIGHT
    if a.lightwrap > 0:
        small = cv2.resize(bg, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        bgb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (W, H), interpolation=cv2.INTER_LINEAR)
        inv = cv2.GaussianBlur(1.0 - al, (0, 0), 5)
        lw = (np.clip(inv * al * 2.0, 0, 1) * a.lightwrap)[..., None]
        fgp = fgp * (1 - lw) + bgb * lw * al[..., None]
    comp = fgp + bg * (1 - al)[..., None]
    if a.grain > 0:
        g = rng.standard_normal((H // 2, W // 2), dtype=np.float32) * a.grain
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
        # зерно сильнее в средних тонах, как у сенсора
        comp = comp + g * (0.5 + 0.5 * (1 - np.abs(comp * 2 - 1)))
    out8 = cv2.convertScaleAbs(np.clip(comp, 0, 1), alpha=255.0)
    if a.still is not None:
        cv2.imwrite(a.out, cv2.cvtColor(out8, cv2.COLOR_RGB2BGR))
        n += 1
        break
    wr.stdin.write(out8.tobytes())
    n += 1
    # Кадры прошлого круга иначе живут до следующего присваивания — полгигабайта на 4K
    # в самый тесный момент следующего кадра.
    I = Bp = bgb = lw = inv = g = small = rb = exc = l = None
    del fgp, al, bg, comp, out8, raw
    if a.kusok and n % 10 == 0:
        Path(a.out).with_suffix(".n").write_text(str(n))
    if n % 90 == 0:
        el = time.time() - started
        log(f"  кадр {n}/{N_KUSKA}  {el / n:.2f} с/кадр")

rf.kill()
ra.kill()
BG.close()
if wr:
    wr.stdin.close()
    wr.wait()
if a.kusok:
    Path(a.out).with_suffix(".n").write_text(str(n))
    Path(a.out).with_suffix(".json").write_text(json.dumps(
        {"n": n, "holes_fixed": int(holes_fixed), "frames_fixed": int(frames_fixed),
         "sek": round(time.time() - started, 1)}), encoding="utf-8")
    # Последнему куску может не хватить кадра-двух: исходник кончился раньше расчётного.
    # Кусок целый — код 0, иначе сборка пересоберёт его зря и упадёт на том же месте.
    hvost_ok = F1 >= BG_N - BG_I and n > 0 and N_KUSKA - n <= 2
    sys.exit(0 if (n == N_KUSKA or hvost_ok) and (not wr or wr.returncode == 0) else 1)
if a.video and tracker:
    log(f"дыры в маске закрыты: {frames_fixed} кадров, {holes_fixed} пикселей")
log(f"готово: {n} кадров за {(time.time() - started):.0f} с → {a.out}")
