#!/usr/bin/env python3
"""
Замена фона в видео — вторая версия (16.09.2026).

Нейросеть RobustVideoMatting даёт грубую маску человека. Дальше — приёмы кеинг-программ
(matte_core.py), без них на стене цвета кожи получались ореол, рваный край и мерцание:

  1. чистая подложка стены из всего ролика (clean plate);
  2. ключ по известному фону: край там, где кадр перестаёт быть стеной;
  3. подавление дрожи маски во времени по оптическому потоку;
  4. очистка цвета края без деления на альфу;
  5. фон без рывка петли, с правильной частотой кадров, с глубиной резкости.

БЕЗОПАСНОЕ КАДРИРОВАНИЕ осталось: если человек обрезан краем исходника, уменьшать
его нельзя — срез уедет внутрь кадра. Режим --fit auto это стережёт.

  python matte.py --video in.mp4 --bg bg.mp4 --out out.mp4
  python matte.py --video in.mp4 --bg green --from 3 --to 6 --out check.mp4 --check runs/.../fon   # проба края

Длинный ролик считается кусками одновременно (--workers, 18.09.2026): нейросеть и
арифметика по кадру одним процессом занимали малую часть ядер, а на кадр уходило
1.1–1.4 с. Куски — те же кадры тем же кодом: подложка стены строится один раз в
родителе, разведка краёв — тоже (все куски кадрируют одинаково), а перед своим
началом каждый кусок разгоняет то, что помнит прошлый кадр — нейросеть, подложку
и подавление дрожи — на RAZGON кадрах, которые не пишутся. Куски склеиваются без
перекодирования, звук подкладывается один раз. Сколько кусков — решают ядра,
выданные очередью, и свободная память; --workers 1 — как раньше, одним процессом.
"""
if __name__ == "__main__":  # М-44: мимо очереди тяжёлое не идёт — перезапуск через неё
    import ochered
    ochered.v_ocheredi()
import argparse, gc, json, os, shutil, subprocess, sys, time
from pathlib import Path
import numpy as np
import onnxruntime as ort
import cv2
from PIL import Image
if hasattr(sys.stdout, "reconfigure"):  # консоль cp1251 роняла вывод со знаками «→», «×», «≈»
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from matte_core import (probe, reader, read_frame, build_plate, PlateTracker, refine_with_plate,
                        foreground_colors, ChatterReducer, Background, choke, repair_holes,
                        svobodno_gb, potoki_ocheredi)

RAZGON = 30          # кадров разгона перед куском: у подложки сглаживание 0.85, за 30 кадров старт забыт (0.85^30 < 1%)
RAZGON_DROZH = 12    # из них дрожь маски нужна лишь на последних: 0.55 за кадр, за 12 кадров старт забыт (< 0.1%)
# ГБ фиксации на мегапиксель кадра у одного куска с его ffmpeg при двух выходах (--out и --alpha-out).
# Замер 18.09.2026, видео 10, 1080p: 1.75–2.24 ГБ на кусок при 2, 4 и 9 потоках (потоки память не меняют);
# третий выход (--fg-out) — ещё ×1.5 (прежний замер: 3.3 ГБ на кусок). Прежние 0.60 занижали вдвое.
GB_NA_MP = 1.1
GB_FG_KOEF = 1.5     # множитель на третий выход --fg-out
ZAPAS_GB = 2.0       # сколько памяти не трогать: рядом живут ферма и чаты
KUSKOV_MAKS = 8

p = argparse.ArgumentParser()
p.add_argument("--video", required=True)
p.add_argument("--bg", required=True, help="картинка, видео или green — проверка края на зелёном")
p.add_argument("--out", required=True)
p.add_argument("--model", default=str(Path(__file__).resolve().parent.parent / "models" / "rvm_mobilenetv3_fp32.onnx"))
p.add_argument("--downsample", type=float, default=0.4)
p.add_argument("--fps", type=float, default=0.0, help="0 — как у исходника")
p.add_argument("--from", dest="t0", type=float, default=None, help="обработать кусок: начало, с")
p.add_argument("--to", dest="t1", type=float, default=None, help="обработать кусок: конец, с")
# вырезка
p.add_argument("--plate", choices=["auto", "off"], default="auto", help="ключ по чистой подложке стены")
p.add_argument("--plate-from", default="", help="видео, по которому строить подложку (по умолчанию --video)")
p.add_argument("--plate-cache", default="", help="npz: сохранить или взять готовую подложку")
p.add_argument("--plate-strength", type=float, default=1.0)
p.add_argument("--chatter", type=float, default=0.55, help="0..0.8: подавление дрожи маски во времени")
p.add_argument("--shrink", type=float, default=0.04, help="подрезка полупрозрачной кромки")
p.add_argument("--choke", type=int, default=1, help="подрезать маску внутрь на столько пикселей (светлая кромка)")
p.add_argument("--edge-soft", type=float, default=0.6, help="размытие кромки маски, px")
p.add_argument("--despill", type=float, default=0.0, help="0..1 снятие зелёного отлива — только для зелёного фона")
# внешний вид
p.add_argument("--grade", default="1.0,1.0,1.0", help="множители R,G,B под свет фона")
p.add_argument("--exposure", type=float, default=1.0)
p.add_argument("--head", default="", help="x,y,w,h лица в долях кадра (из quality.py): центр света")
p.add_argument("--relight", type=float, default=0.0, help="0..1: ниже лица человек темнее, как под лампой")
p.add_argument("--lightwrap", type=float, default=0.2, help="0..1: свет фона на кромке")
# фон
p.add_argument("--bg-blur", type=float, default=0.0, help="глубина резкости фона, sigma в px")
p.add_argument("--bg-slow", type=float, default=1.0, help="замедлить видео фона во столько раз")
p.add_argument("--bg-zoom", type=float, default=1.0)
p.add_argument("--bg-dx", type=int, default=0)
p.add_argument("--bg-push", type=float, default=0.04, help="наезд на картинку фона за ролик")
# кадрирование
p.add_argument("--scale", type=float, default=1.0)
p.add_argument("--dx", type=int, default=0)
p.add_argument("--dy", type=int, default=0)
p.add_argument("--fit", choices=["auto", "free"], default="auto", help="auto: не даёт показать срез на краях исходника")
p.add_argument("--feather", type=int, default=14, help="затухание альфы у срезанных краёв исходника, px")
# проверка
p.add_argument("--alpha-out", default="", help="записать маску отдельным видео (.mkv — без потерь)")
p.add_argument("--fg-out", default="",
               help="записать человека отдельным слоем (цвет, умноженный на маску); фон потом подставляет fon_compose.py")
p.add_argument("--check", default="", help="папка: кадры проверки края (голова крупно на зелёном и на фоне, низ кадра)")
p.add_argument("--workers", type=int, default=0,
               help="сколько кусков считать одновременно: 0 — решить по ядрам и памяти, 1 — одним процессом")
p.add_argument("--kusok", default="", help=argparse.SUPPRESS)  # служебное: "с кадра,до кадра" общей нумерации
p.add_argument("--kraya", default="", help=argparse.SUPPRESS)  # служебное: касание краёв "лево,право,низ,верх" — решил родитель
p.add_argument("--quiet", action="store_true")
# старые флаги первой версии — больше не нужны
for old in ("--unmix", "--unmix-t", "--fill-holes"):
    p.add_argument(old, default=None, help="устарел: заменён ключом по подложке")
a = p.parse_args()


def log(*x):
    if not a.quiet:
        print(*x, flush=True)


for old in ("unmix", "unmix_t", "fill_holes"):
    if getattr(a, old) is not None:
        log(f"  ! --{old.replace('_', '-')} устарел и не действует: край и дыры теперь решает ключ по подложке стены")

W, H, src_fps, dur = probe(a.video)
FPS = a.fps or src_fps
t0 = a.t0 or 0.0
t1 = min(a.t1, dur) if a.t1 else dur
N = int(round((t1 - t0) * FPS))
NMAX = N + 1         # кадров в ролике не больше N + 1: столько мог брать и проход одним процессом
POTOKI_KUSKA = max(1, int(os.environ.get("REELS_MATTE_POTOKI") or 2))   # потоки одного куска (пишет родитель)


def skolko_kuskov() -> int:
    if a.kusok:
        return 1
    if a.workers > 0:
        return max(1, min(a.workers, N // 30 or 1))
    if N < 150:                            # проба в несколько секунд быстрее одним процессом: разгон куска — 30 кадров
        return 1
    gb_kusok = GB_NA_MP * (GB_FG_KOEF if a.fg_out else 1.0) * W * H / 1e6
    po_pamyati = int((svobodno_gb() - ZAPAS_GB) / gb_kusok)
    zhelaemo = min(potoki_ocheredi() // 3, KUSKOV_MAKS, N // 60)
    if po_pamyati < zhelaemo:
        log(f"  ! память держит число кусков: свободно {svobodno_gb():.1f} ГБ (запас {ZAPAS_GB:.0f}), куску нужно "
            f"≈{gb_kusok:.1f} ГБ — влезает {max(1, po_pamyati)}, а хотелось бы {zhelaemo}. Закрыть лишние чаты и "
            f"Chrome — будет быстрее.")
    return max(1, min(zhelaemo, po_pamyati))


K = skolko_kuskov()
F0, F1 = 0, NMAX                   # какие кадры этот процесс считает; у куска — его границы в общей нумерации
if a.kusok:
    F0, F1 = (int(x) for x in a.kusok.split(","))
N_KUSKA = F1 - F0

so = ort.SessionOptions()
if a.kusok:
    # Кусков несколько, и каждый с нейросетью, которая по умолчанию хватает все ядра, — куски
    # передрались бы за процессор. Потоки куска ограничены, и пустое ожидание потоков выключено.
    so.intra_op_num_threads = POTOKI_KUSKA
    so.inter_op_num_threads = 1
    so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    try:
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
    except Exception:
        pass
    cv2.setNumThreads(POTOKI_KUSKA)
sess = ort.InferenceSession(a.model, sess_options=so, providers=["CPUExecutionProvider"])
DSR = np.array([a.downsample], np.float32)
DSR_HALF = np.array([min(1.0, a.downsample * 2)], np.float32)
ZERO = [np.zeros((1, 1, 1, 1), np.float32)] * 4


def rvm(frame, rec, dsr=DSR):
    fgr, pha, *rec = sess.run(["fgr", "pha", "r1o", "r2o", "r3o", "r4o"],
                              {"src": frame.transpose(2, 0, 1)[None], "r1i": rec[0], "r2i": rec[1],
                               "r3i": rec[2], "r4i": rec[3], "downsample_ratio": dsr})
    return pha[0, 0], rec


# ================= 1. РАЗВЕДКА: касается ли человек краёв кадра =================
def probe_edges(n=5):
    rec = ZERO
    rd = reader(a.video, W, H, ss=t0 if t0 else None)
    hits = {"left": 0.0, "right": 0.0, "bottom": 0.0, "top": 0.0}
    got = idx = 0
    while got < n:
        fr = read_frame(rd, W, H)
        if fr is None:
            break
        idx += 1
        if idx % 12:
            continue
        al, rec = rvm(fr, rec)
        hits["left"] = max(hits["left"], (al[:, :2] > 0.5).mean())
        hits["right"] = max(hits["right"], (al[:, -2:] > 0.5).mean())
        hits["bottom"] = max(hits["bottom"], (al[-2:, :] > 0.5).mean())
        hits["top"] = max(hits["top"], (al[:2, :] > 0.5).mean())
        got += 1
    rd.kill()
    return {k: v > 0.01 for k, v in hits.items()}


scale, dx, dy = a.scale, a.dx, a.dy
edges = {"left": False, "right": False, "bottom": False, "top": False}
if a.kraya:                       # кусок: разведку и кадрирование решил родитель — у всех кусков одно
    edges = dict(zip(edges, (v == "1" for v in a.kraya.split(","))))
if a.fit == "auto":
    edges = probe_edges()
    log(f"разведка кадра: касание краёв {', '.join(k for k, v in edges.items() if v) or 'нет'}")
    nw = W * scale
    if edges["left"] and edges["right"] and scale < 1.0:
        log(f"  ! человек обрезан слева и справа — масштаб {scale} показал бы срез, поднимаю до 1.0")
        scale, nw = 1.0, W
    ox = (W - nw) / 2 + dx
    if edges["left"] and ox > 0:
        log(f"  ! левый срез уехал бы внутрь кадра — сдвигаю влево на {int(ox)}px")
        dx -= int(ox)
    ox = (W - nw) / 2 + dx
    if edges["right"] and ox + nw < W:
        log("  ! правый срез уехал бы внутрь кадра — сдвигаю вправо")
        dx += int(W - (ox + nw))
    nh = H * scale
    oy = (H - nh) + dy
    if edges["bottom"] and oy + nh < H:
        log("  ! нижний срез уехал бы внутрь кадра — прижимаю к низу")
        dy += int(H - (oy + nh))

# ================= 2. ПОДЛОЖКА СТЕНЫ =================
tracker = None
if a.plate == "auto":
    P = None
    cache = Path(a.plate_cache) if a.plate_cache else None
    if cache and cache.exists():
        z = np.load(cache)
        P = {"plate": z["plate"], "seen": z["seen"], "conf": z["conf"], "q": int(z["q"])}
        log(f"подложка стены: из {cache}")
    else:
        started = time.time()
        src = a.plate_from or a.video
        P = build_plate(src, W, H, lambda fr: rvm(fr, ZERO, DSR_HALF)[0], log=log)
        log(f"  построена за {time.time() - started:.0f} с")
        if P and cache:
            np.savez_compressed(cache, plate=P["plate"], seen=P["seen"], conf=P["conf"], q=P["q"])
    if P is not None:
        tracker = PlateTracker(P, W, H)
    else:
        log("  ! стена не найдена — работаю только по нейросети")


# ================= 2б. КУСКАМИ: раздать ролик процессам =================
def sobrat_kuskami(k: int) -> int:
    """Раздать ролик k процессам, дождаться, склеить без перекодирования, подложить звук.
    Всё общее — кадрирование, края, подложка — решено выше, до раздачи; куски его получают готовым."""
    global sess
    sess = None                     # нейросеть родителю больше не нужна, а память кусков на счету
    gc.collect()
    started = time.time()
    papka = Path(a.out).with_name(Path(a.out).stem + ".kuski")
    shutil.rmtree(papka, ignore_errors=True)
    papka.mkdir(parents=True)
    granicy = [round(i * N / k) for i in range(k)] + [NMAX]   # последний кусок берёт и лишний кадр, если он есть
    na_kusok = max(1, potoki_ocheredi() // k)
    env = dict(os.environ, REELS_MATTE_POTOKI=str(na_kusok))
    for imya in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[imya] = str(na_kusok)
    log(f"вырезка кусками: {k} одновременно по {na_kusok} потока, {N} кадров {W}x{H}, "
        f"свободной памяти {svobodno_gb():.1f} ГБ")

    obshee = ["--fit", "free", "--scale", repr(float(scale)), "--dx", str(int(dx)), "--dy", str(int(dy)),
              "--kraya", ",".join("1" if edges[e] else "0" for e in ("left", "right", "bottom", "top"))]
    if a.plate == "auto":
        if P is None:
            obshee += ["--plate", "off"]           # стены нет — куски не ищут её заново
        else:
            kesh = Path(a.plate_cache) if a.plate_cache else papka / "plate.npz"
            if not kesh.exists():
                np.savez_compressed(kesh, plate=P["plate"], seen=P["seen"], conf=P["conf"], q=P["q"])
            obshee += ["--plate-cache", str(kesh)]

    kuski = [papka / f"kusok_{i:02d}.mp4" for i in range(k)]
    kuski_a = [papka / f"kusok_{i:02d}.alpha{Path(a.alpha_out).suffix}" for i in range(k)] if a.alpha_out else []
    kuski_f = [papka / f"kusok_{i:02d}.fg.mp4" for i in range(k)] if a.fg_out else []

    def pusk(i: int) -> tuple:
        argv = [sys.executable, str(Path(__file__).resolve())] + sys.argv[1:] + obshee + [
            "--out", str(kuski[i]), "--workers", "1", "--quiet", "--kusok", f"{granicy[i]},{granicy[i + 1]}"]
        if a.alpha_out:
            argv += ["--alpha-out", str(kuski_a[i])]
        if a.fg_out:
            argv += ["--fg-out", str(kuski_f[i])]
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
        time.sleep(1.5)     # не все разом: на старте у каждого куска всплеск памяти
    zhdat(raboty)
    # Упавший кусок (обычно не хватило памяти, пока шли все разом) пересчитывается один.
    upali = [i for i, (r, _) in enumerate(raboty) if r.returncode != 0]
    for i in upali:
        log(f"  кусок {i} не собрался (код {raboty[i][0].returncode}) — пересчитываю его отдельно")
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
    # Все куски, кроме последнего, обязаны быть целыми: иначе следующий начался не с того кадра.
    # Последний кончается там, где кончился исходник, — как и проход одним процессом.
    if not all(itogi[i]["n"] == granicy[i + 1] - granicy[i] for i in range(k - 1)):
        print(f"куски собраны не полностью: {[x['n'] for x in itogi]} из "
              f"{[granicy[i + 1] - granicy[i] for i in range(k)]}; журналы — {papka}", file=sys.stderr, flush=True)
        return 1
    if sdelano < N:
        log(f"  ! кадров в ролике {sdelano}, а расчёт по длительности — {N}: видеодорожка короче на {N - sdelano}")

    ss_a = f"-ss {t0} " if t0 else ""
    to_a = f"-t {t1 - t0} " if a.t1 else ""

    def sklejit(chunks: list, final: str, zvuk: str) -> int:
        spisok = papka / (Path(final).name + ".spisok.txt")
        spisok.write_text("".join(f"file '{c.resolve().as_posix()}'\n" for c in chunks), encoding="utf-8")
        if zvuk:   # звук — один раз, из исходника, как при проходе одним процессом
            cmd = (f'ffmpeg -v error -f concat -safe 0 -i "{spisok}" {ss_a}{to_a}-i "{a.video}" -map 0:v -map 1:a? '
                   f'-c:v copy -c:a aac -b:a {zvuk} -shortest "{final}" -y')
        else:
            cmd = f'ffmpeg -v error -f concat -safe 0 -i "{spisok}" -c copy "{final}" -y'
        return subprocess.call(cmd, shell=True)

    zadachi = [(kuski, a.out, "192k")]
    if a.alpha_out:
        zadachi.append((kuski_a, a.alpha_out, ""))
    if a.fg_out:
        zadachi.append((kuski_f, a.fg_out, "256k"))
    for chunks, final, zvuk in zadachi:
        kod = sklejit(chunks, final, zvuk)
        if kod != 0:
            print(f"склейка кусков в {final} не удалась (код {kod}); куски — {papka}", file=sys.stderr, flush=True)
            return 1
    shutil.rmtree(papka, ignore_errors=True)
    el = time.time() - started
    log(f"склеек в исходнике (маска не смешивалась через них): {sum(x.get('cuts', 0) for x in itogi)}")
    spent = {}
    for x in itogi:
        for imya, v in x.get("spent", {}).items():
            spent[imya] = spent.get(imya, 0.0) + v
    if sdelano and spent:
        log("время на кадр в кусках: " + ", ".join(f"{imya} {v / sdelano:.2f} с" for imya, v in spent.items()))
    log("куски, с: " + ", ".join(f"{x['sek']:.0f}" for x in itogi))
    log(f"готово: {sdelano} кадров за {el / 60:.1f} мин ({el / max(sdelano, 1):.2f} с/кадр, кусков {k}) → {a.out}")
    return 0


if not a.kusok and K > 1:
    sys.exit(sobrat_kuskami(K))

# ================= 3. ФОН, КРАЯ, СВЕТ =================
GREEN = a.bg.lower() == "green"
BGsrc = None if GREEN else Background(a.bg, W, H, N, fps=FPS, blur=a.bg_blur, slow=a.bg_slow,
                                      zoom=a.bg_zoom, dx=a.bg_dx, push=a.bg_push, log=log)
if a.kusok and BGsrc is not None:
    BGsrc.skip(F0)                 # фон идёт по общему счёту кадров ролика: наезд и петля не начинаются заново
green = np.zeros((H, W, 3), np.float32)
green[..., 1] = 0.69
green[..., 2] = 0.25

edge_mask = np.ones((H, W), np.float32)
# Растушёвка нужна, только когда срез исходника может оказаться внутри кадра
# (человек уменьшен или сдвинут). При масштабе 1 край кадра и есть край среза —
# растушёвка лишь делала руку у края полупрозрачной.
if a.feather > 0 and (scale < 1.0 or dx or dy):
    f = a.feather
    ramp = np.linspace(0, 1, f, dtype=np.float32)
    if edges.get("left"):
        edge_mask[:, :f] *= ramp[None, :]
    if edges.get("right"):
        edge_mask[:, -f:] *= ramp[::-1][None, :]
    if edges.get("top"):
        edge_mask[:f, :] *= ramp[:, None]

LIGHT = None
if a.relight > 0:
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None]
    fy = float(a.head.split(",")[1]) if a.head else 0.35
    ramp = np.clip((yy - fy) / (1.0 - fy), 0, 1)
    LIGHT = (1.0 - a.relight * ramp ** 1.2)[..., None] * np.ones((1, W, 1), np.float32)

HEADBOX = None
if a.head:
    hx, hy, hw_, hh_ = (float(v) for v in a.head.split(","))
    HEADBOX = (int((hx - 0.9 * hw_) * W), int((hy - 1.0 * hh_) * H), int(1.8 * hw_ * W), int(1.6 * hh_ * H))

gr = np.array([float(x) for x in a.grade.split(",")], np.float32).reshape(1, 1, 3)
chatter = ChatterReducer(W, H, strength=a.chatter)

# ================= 4. ПРОХОД =================
# Кусок из середины ролика начинает читать раньше на разгон и встаёт между кадрами:
# на полкадра раньше нужного — первым придёт ровно нужный кадр.
RAZGON_K = min(F0, RAZGON) if a.kusok else 0
if a.kusok and F0 - RAZGON_K > 0:
    ss = t0 + (F0 - RAZGON_K - 0.5) / FPS
else:
    ss = t0 if t0 else None
# У куска — декодер с потолком потоков и без выравнивания частоты кадров (иначе первый кадр после
# дробного -ss дублируется и кусок сдвигается на кадр). Конец ролика ставит --to, как и одному процессу.
rd = reader(a.video, W, H, ss=ss, to=a.t1, threads=2 if a.kusok else None, passthrough=bool(a.kusok))
ss_a = f"-ss {t0} " if t0 else ""
to_a = f"-t {t1 - t0} " if a.t1 else ""
# Кусок — только картинка: звук подкладывается один раз при склейке. Потоки кодировщиков
# ограничены: кусков несколько, и кодировщики 1080p всех кусков разом не должны отнять ядра у вырезки.
THR = f"-threads {max(2, POTOKI_KUSKA)} " if a.kusok else ""
if a.kusok:
    wr = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {THR}'
        f'-c:v libx264 -preset medium -crf 17 -pix_fmt yuv420p "{a.out}" -y',
        shell=True, stdin=subprocess.PIPE)
else:
    wr = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - '
        f'{ss_a}{to_a}-i "{a.video}" -map 0:v -map 1:a? -c:v libx264 -preset medium -crf 17 '
        f'-pix_fmt yuv420p -c:a aac -b:a 192k -shortest "{a.out}" -y',
        shell=True, stdin=subprocess.PIPE)
wa = None
if a.alpha_out:
    codec = "-c:v ffv1 -pix_fmt gray" if a.alpha_out.lower().endswith(".mkv") else         "-c:v libx264 -preset fast -crf 12 -pix_fmt yuv420p"
    wa = subprocess.Popen(
        f'ffmpeg -v error -f rawvideo -pix_fmt gray -s {W}x{H} -r {FPS} -i - {THR}{codec} "{a.alpha_out}" -y',
        shell=True, stdin=subprocess.PIPE)
wf = None
if a.fg_out:
    if a.kusok:
        wf = subprocess.Popen(
            f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {THR}'
            f'-c:v libx264 -preset medium -crf 8 -pix_fmt yuv444p "{a.fg_out}" -y', shell=True, stdin=subprocess.PIPE)
    else:
        wf = subprocess.Popen(
            f'ffmpeg -v error -f rawvideo -pix_fmt rgb24 -s {W}x{H} -r {FPS} -i - {ss_a}{to_a}-i "{a.video}" '
            f'-map 0:v -map 1:a? -c:v libx264 -preset medium -crf 8 -pix_fmt yuv444p -c:a aac -b:a 256k '
            f'-shortest "{a.fg_out}" -y', shell=True, stdin=subprocess.PIPE)

check_at = set()
if a.check:
    Path(a.check).mkdir(parents=True, exist_ok=True)
    check_at = {int(N * k / 5) for k in range(1, 5)}       # номера кадров — в общей нумерации ролика

rec = ZERO
n = 0
started = time.time()
spent = {}
mark = [time.time()]


def tick(name):
    now = time.time()
    spent[name] = spent.get(name, 0.0) + now - mark[0]
    mark[0] = now


cuts0 = 0
if RAZGON_K:
    # Разгон: то, что помнит прошлый кадр, — нейросеть, подложка стены, дрожь маски, — привыкает к
    # ролику на кадрах перед куском. Считается тем же кодом, что основной проход; кадры не пишутся.
    for j in range(RAZGON_K):
        I = read_frame(rd, W, H)
        if I is None:
            break
        a_nn, rec = rvm(I, rec)
        B = tracker.frame(I, a_nn) if tracker is not None else None
        if j >= RAZGON_K - RAZGON_DROZH:
            chatter(I, a_nn if B is None else refine_with_plate(I, a_nn, B, tracker.conf_full,
                                                                strength=a.plate_strength))
    I = B = a_nn = None
    cuts0 = chatter.cuts


while True:
    mark[0] = time.time()
    I = read_frame(rd, W, H)
    if I is None or n >= N_KUSKA:
        break
    tick("чтение")
    a_nn, rec = rvm(I, rec)
    tick("нейросеть")

    B = None
    alpha = a_nn
    if tracker is not None:
        B = tracker.frame(I, a_nn)
        alpha = refine_with_plate(I, a_nn, B, tracker.conf_full, strength=a.plate_strength)
        tick("ключ по стене")
    alpha = chatter(I, alpha)
    if tracker is not None:
        alpha, _ = repair_holes(I, alpha, B)      # страховка: дыра могла прийти из прошлого кадра
    tick("дрожь")
    if a.shrink > 0:
        alpha = np.clip((alpha - a.shrink) / (1.0 - a.shrink), 0, 1)
    alpha = choke(alpha, a.choke, a.edge_soft)
    alpha = alpha * edge_mask

    F = foreground_colors(I, alpha, plate=B)
    tick("цвет края")
    if a.despill > 0:
        rb = (F[..., 0] + F[..., 2]) * 0.5
        exc = np.maximum(F[..., 1] - rb, 0.0)
        F[..., 1] -= exc * a.despill
        F = np.clip(F + (exc * a.despill * 0.35)[..., None], 0, 1)

    if scale != 1.0 or dx or dy:
        nw, nh = int(W * scale), int(H * scale)
        fi = cv2.resize(F, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        ai = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        cf = np.zeros((H, W, 3), np.float32)
        ca = np.zeros((H, W), np.float32)
        ox, oy = (W - nw) // 2 + dx, (H - nh) + dy
        sx0, sy0, dx0, dy0 = max(0, -ox), max(0, -oy), max(0, ox), max(0, oy)
        cw, ch = min(nw - sx0, W - dx0), min(nh - sy0, H - dy0)
        if cw > 0 and ch > 0:
            cf[dy0:dy0 + ch, dx0:dx0 + cw] = fi[sy0:sy0 + ch, sx0:sx0 + cw]
            ca[dy0:dy0 + ch, dx0:dx0 + cw] = ai[sy0:sy0 + ch, sx0:sx0 + cw]
        F, alpha = cf, np.clip(ca, 0, 1)

    F = np.clip(F * gr * a.exposure, 0, 1)
    if LIGHT is not None:
        F = np.clip(F * LIGHT, 0, 1)

    if wf:
        wf.stdin.write(cv2.convertScaleAbs(F * alpha[..., None], alpha=255.0).tobytes())
    bg = green if GREEN else BGsrc.next()
    tick("фон")
    al = alpha[..., None]
    if a.lightwrap > 0 and not GREEN:
        # свет фона заходит на кромку изнутри: размытый фон поверх края человека
        small = cv2.resize(bg, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
        bgb = cv2.resize(cv2.GaussianBlur(small, (0, 0), 3), (W, H), interpolation=cv2.INTER_LINEAR)
        inv = cv2.GaussianBlur(1.0 - alpha, (0, 0), 5)
        lw = np.clip(inv * alpha * 2.0, 0, 1)[..., None] * a.lightwrap
        F = F * (1 - lw) + bgb * lw

    comp = cv2.blendLinear(np.ascontiguousarray(F, np.float32), np.ascontiguousarray(bg, np.float32),
                           alpha, (1.0 - alpha).astype(np.float32))
    out8 = cv2.convertScaleAbs(comp, alpha=255.0)
    wr.stdin.write(out8.tobytes())
    if wa:
        wa.stdin.write((np.clip(alpha, 0, 1) * 255).astype(np.uint8).tobytes())

    if F0 + n in check_at:
        base = Path(a.check) / f"k{F0 + n:04d}"
        cv2.imwrite(str(base) + "-kadr.jpg", cv2.cvtColor(cv2.resize(out8, (W // 2, H // 2)), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        gcomp = (np.clip(F * al + green * (1 - al), 0, 1) * 255).astype(np.uint8)
        if HEADBOX:
            x, y, bw, bh = HEADBOX
            x, y = max(0, x), max(0, y)
            crop = np.concatenate([gcomp[y:y + bh, x:x + bw], out8[y:y + bh, x:x + bw]], axis=1)
            cv2.imwrite(str(base) + "-golova.png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        low = np.concatenate([gcomp[H - 560:, :], out8[H - 560:, :]], axis=0)
        cv2.imwrite(str(base) + "-niz.jpg", cv2.cvtColor(cv2.resize(low, (W // 2, 560)), cv2.COLOR_RGB2BGR),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    tick("сведение и запись")
    n += 1
    if a.kusok and n % 10 == 0:
        Path(a.out).with_suffix(".n").write_text(str(n))
    if n % 60 == 0:
        el = time.time() - started
        log(f"  кадр {n}/{N}  {el / n:.2f} с/кадр, осталось ≈{(N - n) * el / n / 60:.1f} мин")

wr.stdin.close()
wr.wait()
if wa:
    wa.stdin.close()
    wa.wait()
if wf:
    wf.stdin.close()
    wf.wait()
rd.kill()
if BGsrc:
    BGsrc.close()
if a.kusok:
    Path(a.out).with_suffix(".n").write_text(str(n))
    Path(a.out).with_suffix(".json").write_text(json.dumps(
        {"n": n, "cuts": chatter.cuts - cuts0, "sek": round(time.time() - started, 1),
         "spent": {imya: round(v, 2) for imya, v in spent.items()}}), encoding="utf-8")
    # Целый кусок — код 0. Последнему можно кончиться раньше расчёта: исходник кончился, как и при
    # проходе одним процессом. Остальные обязаны быть целыми, иначе следующий начался бы не с того кадра.
    ok = (n == N_KUSKA or (F1 >= NMAX and n > 0)) and all(w is None or w.returncode == 0 for w in (wr, wa, wf))
    sys.exit(0 if ok else 1)
log(f"склеек в исходнике (маска не смешивалась через них): {chatter.cuts}")
if n:
    log("время на кадр: " + ", ".join(f"{k} {v / n:.2f} с" for k, v in spent.items()))
log(f"готово: {n} кадров за {(time.time() - started) / 60:.1f} мин → {a.out}")
