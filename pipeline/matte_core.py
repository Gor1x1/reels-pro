"""
Приёмы профессиональной вырезки для matte.py.

Здесь то, чем кеинг-программы отличаются от «нейросеть дала маску — наклеили»:

  чистая подложка (clean plate) — как выглядит стена без человека;
  ключ по известному фону — край там, где кадр перестаёт быть стеной;
  очистка цвета края (decontaminate edge colors) — без ободка цвета старой стены;
  подавление дрожи маски во времени (reduce chatter) — по движению, без шлейфа;
  фон без склейки петли и с глубиной резкости.

Всё считается на процессоре: видеокарта GT 740 не тянет нейросети.
"""
import subprocess, json
import numpy as np
import cv2


def smoothstep(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def probe(path):
    """Ширина, высота, fps и длительность видео."""
    out = subprocess.check_output(
        f'ffprobe -v error -select_streams v:0 -show_entries stream=width,height,r_frame_rate:format=duration '
        f'-of json "{path}"', shell=True)
    j = json.loads(out)
    st = j["streams"][0]
    num, den = (int(x) for x in st["r_frame_rate"].split("/"))
    return int(st["width"]), int(st["height"]), num / max(den, 1), float(j["format"]["duration"])


def reader(path, W, H, vf="", ss=None, to=None, loop=False):
    pre = f"-ss {ss} " if ss is not None else ""
    post = f"-to {to - (ss or 0)} " if to is not None else ""
    lp = "-stream_loop -1 " if loop else ""
    chain = f'-vf "{vf}" ' if vf else ""
    return subprocess.Popen(
        f'ffmpeg -v error {lp}{pre}-i "{path}" {post}{chain}-f rawvideo -pix_fmt rgb24 -',
        shell=True, stdout=subprocess.PIPE, bufsize=W * H * 3 * 4)


def read_frame(proc, W, H):
    raw = proc.stdout.read(W * H * 3)
    if len(raw) < W * H * 3:
        return None
    return np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0


# ============================ ЧИСТАЯ ПОДЛОЖКА ============================

def poly_fill(img, weight, deg=3):
    """Гладкая поверхность стены по видимым пикселям: полином по x, y на каждый канал."""
    h, w = weight.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx = xx / w * 2 - 1
    yy = yy / h * 2 - 1
    terms = [xx ** i * yy ** j for i in range(deg + 1) for j in range(deg + 1 - i)]
    A = np.stack([t.ravel() for t in terms], 1)
    wv = weight.ravel()
    sel = wv > 0
    if sel.sum() < len(terms) * 20:
        return None
    Aw = A[sel] * wv[sel, None]
    out = np.empty_like(img)
    for c in range(img.shape[2]):
        coef, *_ = np.linalg.lstsq(Aw, img[..., c].ravel()[sel] * wv[sel], rcond=None)
        out[..., c] = (A @ coef).reshape(h, w)
    return out


def robust_poly(img, weight, deg=4, iters=4, scale=0.03):
    """Полином стены, нечувствительный к выбросам: пиксели, далёкие от поверхности, теряют вес."""
    wv = weight.copy()
    fit = None
    for _ in range(iters):
        fit = poly_fill(img, wv, deg)
        if fit is None:
            return None
        r = np.abs(img - fit).max(axis=2)
        wv = weight / (1.0 + (r / scale) ** 2)
    return fit


def build_plate(video, W, H, alpha_single, n_samples=160, q=4, log=print, t0=None, t1=None):
    """
    Подложка стены из всего ролика. На каждом взятом кадре нейросеть говорит, где
    человек; пиксели уверенной стены копятся. Стена гладкая, поэтому сначала
    строится устойчивый полином, и в медиану идут только отсчёты, близкие к нему:
    на рилсе 1 сеть в трети кадров принимала белую футболку за стену, и простая
    медиана рисовала футболку на подложке — ключ потом дырявил человека.
    """
    _, _, fps, dur = probe(video)
    a = t0 or 0.0
    b = min(t1 or dur, dur)
    total = int((b - a) * fps)
    step = max(1, total // n_samples)
    hw, hh = W // 2, H // 2
    w, h = W // q, H // q
    rd = reader(video, hw, hh, vf=f"scale={hw}:{hh}", ss=a if a > 0 else None, to=b if t1 else None)
    frames, masks, empty = [], [], []
    k = 0
    edge = int(3 * fps)                     # начало и конец записи — чаще: там бывает пустой кадр
    while True:
        fr = read_frame(rd, hw, hh)
        if fr is None:
            break
        if k % step == 0 or ((k < edge or k > total - edge) and k % 3 == 0):
            al = alpha_single(fr)
            sm = cv2.resize(fr, (w, h), interpolation=cv2.INTER_AREA)
            am = cv2.resize(al, (w, h), interpolation=cv2.INTER_AREA)
            if (al > 0.5).mean() < 0.003:
                empty.append(sm)
            wall = (am < 0.02).astype(np.uint8)
            wall = cv2.erode(wall, np.ones((3, 3), np.uint8), iterations=2)
            frames.append(sm.astype(np.float16))
            masks.append(wall.astype(bool))
        k += 1
    rd.stdout.close()
    rd.wait()
    if not frames:
        return None
    F = np.stack(frames).astype(np.float32)
    M = np.stack(masks)
    n = len(frames)
    F[~M] = np.nan

    # Лучшая подложка — кадры, где человека нет вовсе (включил запись и вошёл в кадр).
    if len(empty) >= 6:
        E = np.median(np.stack(empty), axis=0).astype(np.float32)
        # проверка: камера не сдвинулась и свет тот же — стена в разговорной части
        # совпадает с пустым кадром с точностью до общей яркости
        talk = np.nanmedian(F, axis=0)
        ok = np.isfinite(talk).all(axis=2) & (M.sum(axis=0) >= max(8, int(0.3 * n)))
        if ok.sum() > 500:
            g = np.median(talk[ok] / np.maximum(E[ok], 0.03), axis=0)
            dev = float(np.median(np.abs(talk[ok] - E[ok] * g)))
            if dev < 0.03:
                log(f"подложка стены: {len(empty)} пустых кадров без человека, расхождение с разговорной "
                    f"частью {dev:.3f} — берём их")
                return {"plate": E, "seen": np.ones((h, w), np.float32), "conf": np.ones((h, w), np.float32), "q": q}
            log(f"  пустые кадры есть ({len(empty)}), но стена в них другая (расхождение {dev:.3f}) — "
                f"камеру сдвинули или свет поменялся; строю по разговорной части")

    med0 = np.nanmedian(F, axis=0)
    cnt0 = M.sum(axis=0)
    trusted0 = cnt0 >= max(8, int(0.3 * n))
    med0[~trusted0] = 0
    poly = robust_poly(med0, trusted0.astype(np.float32))
    if poly is None:
        return None
    # в медиану — только отсчёты, похожие на стену и по яркости, и по оттенку:
    # белая футболка и кожа отличаются от бежевой стены прежде всего оттенком
    chroma = F / np.maximum(F.sum(axis=3, keepdims=True), 1e-3)
    pc = poly / np.maximum(poly.sum(axis=2, keepdims=True), 1e-3)
    close = (np.abs(F - poly[None]).max(axis=3) < 0.08) & (np.abs(chroma - pc[None]).max(axis=3) < 0.03)
    close &= M
    F[~close] = np.nan
    cnt = close.sum(axis=0)
    med = np.nanmedian(F, axis=0)
    have = cnt >= 5
    med[~have] = 0
    wgt = have.astype(np.float32)
    num = cv2.GaussianBlur(med * wgt[..., None], (0, 0), 8)
    den = cv2.GaussianBlur(wgt, (0, 0), 8)[..., None]
    nearfill = num / np.maximum(den, 1e-4)
    mix = smoothstep(den[..., 0], 0.02, 0.25)[..., None]
    filled = nearfill * mix + poly * (1 - mix)
    plate = np.where(have[..., None], med, filled)
    seen = (cnt / n).astype(np.float32)
    # доверие к подложке: видна ли стена рядом (решает «здесь стена»)
    dist = cv2.distanceTransform((~have).astype(np.uint8), cv2.DIST_L2, 3)
    conf = 1.0 - smoothstep(dist * q, 30, 90)
    resid = float(np.abs(med - poly)[have].mean()) if have.any() else 0.0
    log(f"подложка стены: {n} кадров, стена видна на {have.mean() * 100:.0f}% кадра, "
        f"отклонение от гладкой стены {resid:.3f}, отброшено непохожих на стену отсчётов "
        f"{(1 - close.sum() / max(M.sum(), 1)) * 100:.0f}%")
    return {"plate": plate.astype(np.float32), "seen": seen, "conf": conf.astype(np.float32), "q": q}


class PlateTracker:
    """Подложка на каждый кадр: общая яркость камеры плюс локальная тень у человека."""

    def __init__(self, P, W, H, local=True):
        self.P, self.W, self.H, self.local = P, W, H, local
        self.q = P["q"]
        self.gain = None
        self.corr = None
        self.conf_full = cv2.resize(P["conf"], (W, H), interpolation=cv2.INTER_LINEAR)

    def frame(self, I, a_nn):
        q = self.q
        w, h = self.W // q, self.H // q
        Is = cv2.resize(I, (w, h), interpolation=cv2.INTER_AREA)
        As = cv2.resize(a_nn, (w, h), interpolation=cv2.INTER_AREA)
        wall = cv2.erode((As < 0.02).astype(np.uint8), np.ones((3, 3), np.uint8), iterations=2).astype(bool)
        wall &= self.P["seen"] > 0.15
        plate = self.P["plate"]
        if wall.sum() > 300:
            g = np.median(Is[wall] / np.maximum(plate[wall], 0.03), axis=0)
            g = np.clip(g, 0.5, 2.0).astype(np.float32)
            self.gain = g if self.gain is None else self.gain * 0.85 + g * 0.15
        gain = self.gain if self.gain is not None else np.ones(3, np.float32)
        B = plate * gain
        if self.local and wall.sum() > 300:
            R = (Is - B) * wall[..., None]
            num = cv2.GaussianBlur(R, (0, 0), 5)
            den = cv2.GaussianBlur(wall.astype(np.float32), (0, 0), 5)[..., None]
            c = np.clip(num / np.maximum(den, 1e-3), -0.12, 0.12) * smoothstep(den, 0.05, 0.3)
            self.corr = c if self.corr is None else self.corr * 0.6 + c * 0.4
        if self.corr is not None:
            B = B + self.corr
        return cv2.resize(B, (self.W, self.H), interpolation=cv2.INTER_LINEAR)


# ========================= КЛЮЧ ПО ИЗВЕСТНОМУ ФОНУ =========================

def enclosed(solid):
    """
    Силуэт с закрытыми дырами. Фон — то, что связано с верхним, левым или правым
    краем кадра; всё, что замкнуто внутри человека, — внутри, даже если сеть там
    дала прозрачность. Нижний край не считается фоном: человек стоит, его срезает
    низ кадра.
    """
    h, w = solid.shape
    n, lab, st, _ = cv2.connectedComponentsWithStats((solid == 0).astype(np.uint8), connectivity=4)
    left, top, cw = st[:, cv2.CC_STAT_LEFT], st[:, cv2.CC_STAT_TOP], st[:, cv2.CC_STAT_WIDTH]
    outside = (top == 0) | (left == 0) | (left + cw >= w)
    outside[0] = False
    return (solid > 0) | ~outside[lab]


def repair_holes(I, a, B, strength=1.0):
    """
    Дыры в готовой маске: замкнутые внутри силуэта пиксели, явно не цвета стены,
    становятся человеком. Для масок, посчитанных раньше, и как страховка после
    сглаживания во времени.
    """
    H, W = a.shape
    hw, hh = W // 2, H // 2
    a_half = cv2.resize(a, (hw, hh), interpolation=cv2.INTER_AREA)
    solid = (a_half > 0.5).astype(np.uint8)
    inside = enclosed(solid) & (a_half < 0.97)
    if not inside.any():
        return a, 0
    # Маленькая замкнутая дыра (до ~120×120 px) — почти всегда провал сети в одежде:
    # её закрываем всю, кроме пикселей, точно совпадающих со стеной. Большая — может
    # быть настоящим просветом между рукой и телом, там нужен явный «не цвет стены».
    holes = (enclosed(solid) & (solid == 0)).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(holes, connectivity=8)
    small = np.zeros(n, bool)
    small[1:] = st[1:, cv2.CC_STAT_AREA] < 4000
    small_h = cv2.dilate((small[lab] & (holes > 0)).astype(np.uint8), _ELL7)
    inside = cv2.dilate(inside.astype(np.uint8), _ONES3)
    m = cv2.resize(inside, (W, H), interpolation=cv2.INTER_NEAREST) > 0
    ys, xs = np.nonzero(m & (a < 0.97))
    if len(ys) == 0:
        return a, 0
    D = I[ys, xs] - B[ys, xs]
    dist = np.sqrt((D * D).sum(axis=1))
    Ic, Bc = I[ys, xs], B[ys, xs]
    lumI = Ic.mean(axis=1)
    lumB = np.maximum(Bc.mean(axis=1), 1e-3)
    k = lumI / lumB
    chroma = np.sqrt(((Ic / np.maximum(lumI, 1e-3)[:, None] - Bc / lumB[:, None]) ** 2).sum(axis=1))
    shadow = smoothstep(k, 0.35, 0.5) * (1 - smoothstep(k, 0.9, 0.98)) * (1 - smoothstep(chroma, 0.06, 0.12))
    # цвет человека рядом с дырой: одежда вокруг провала в футболке, кожа и
    # футболка вокруг просвета между рукой и телом. Пиксель закрывается, только
    # если по цвету он ближе к человеку рядом, чем к стене: на рилсе 1 без этого
    # в просвет у руки ложились бежевые крапинки стены в тени.
    I_half = cv2.resize(I, (hw, hh), interpolation=cv2.INTER_AREA)
    mf = (a_half > 0.95).astype(np.float32)
    num = cv2.GaussianBlur(I_half * mf[..., None], (0, 0), 8)
    den = cv2.GaussianBlur(mf, (0, 0), 8)
    yh, xh = np.minimum(ys // 2, hh - 1), np.minimum(xs // 2, hw - 1)
    Fl = num[yh, xh] / np.maximum(den[yh, xh], 1e-4)[:, None]
    d_person = np.sqrt(((Ic - Fl) ** 2).sum(axis=1))
    # нужен явный запас: белая футболка отражает свет лампы на стену рядом, и стена
    # в просвете у руки светлее подложки — по цвету как рука в тени (разница 0.04–0.06),
    # а у настоящей дыры в футболке запас около 0.24
    closer = smoothstep(dist - d_person, 0.08, 0.16)
    fill_big = smoothstep(dist, 0.12, 0.22) * (1 - shadow) * closer
    in_small = small_h[yh, xh] > 0
    # тень человека на стене того же оттенка, что стена, — не человек, даже в
    # маленьком просвете: кожа руки в тени и стена в тени по цвету почти равны
    fill = np.where(in_small, np.maximum(closer * (1 - shadow), fill_big), fill_big) * strength
    # решение по всей дыре: маленькая дыра, закрытая больше чем на 60%, — провал в
    # одежде целиком; иначе в её середине остаётся точка, где цвет рядом смешан с рукой
    lab_px = lab[yh, xh]
    if n > 1:
        tot = np.bincount(lab_px, weights=fill, minlength=n)
        cnt = np.bincount(lab_px, minlength=n)
        share = tot / np.maximum(cnt, 1)
        whole = small & (share >= 0.6)
        whole[0] = False
        fill = np.where(whole[lab_px], strength, fill)
    out = a.copy()
    new = np.maximum(a[ys, xs], fill)
    fixed = int((new - a[ys, xs] > 0.3).sum())
    out[ys, xs] = new
    return out, fixed


def refine_with_plate(I, a_nn, B, conf, sep=(0.05, 0.15), strength=1.0):
    """
    Кадр — смесь человека F и стены B: I = a·F + (1-a)·B. Стена известна, цвет
    человека у края берём из уверенных соседей. Там, где человек по цвету далёк
    от стены (волосы, белая футболка, тёмная одежда), альфа считается из этой
    формулы точнее нейросети. Где цвета близки (кожа на бежевой стене) — решает
    нейросеть. Тени на стене человеком не считаются.

    Считается только полоса вокруг человека и провалы маски: уверенная середина
    фигуры и далёкий фон не меняются — в 5 раз быстрее, чем по всему кадру.
    """
    H, W = a_nn.shape
    hw, hh = W // 2, H // 2
    a_half = cv2.resize(a_nn, (hw, hh), interpolation=cv2.INTER_AREA)
    # «рядом с человеком» — от силуэта с закрытыми дырами: на рилсе 1 сеть делала
    # в футболке дыру шире радиуса расширения, её середина выпадала из проверки,
    # и сквозь грудь светила лампа нового фона
    near_h = cv2.dilate(enclosed((a_half > 0.1).astype(np.uint8)).astype(np.uint8), _ELL25)
    # середина фигуры, где сеть уверена, ключом не режется: кожа по цвету как
    # стена, и без защиты через лицо просвечивал фон
    inner_h = cv2.erode((a_half > 0.97).astype(np.uint8), _ELL7)
    cand_h = ((near_h > 0) & (inner_h == 0)).astype(np.uint8)
    cand = cv2.resize(cand_h, (W, H), interpolation=cv2.INTER_NEAREST) > 0
    ys, xs = np.nonzero(cand)
    if len(ys) == 0:
        return a_nn

    # цвет человека у края — из уверенной внутренней части (половинное разрешение)
    I_half = cv2.resize(I, (hw, hh), interpolation=cv2.INTER_AREA)
    m = cv2.erode((a_half > 0.95).astype(np.uint8), _ONES3).astype(np.float32)
    num = cv2.GaussianBlur(I_half * m[..., None], (0, 0), 6)
    den = cv2.GaussianBlur(m, (0, 0), 6)
    yh, xh = np.minimum(ys // 2, hh - 1), np.minimum(xs // 2, hw - 1)
    dc = den[yh, xh]
    Fh = num[yh, xh] / np.maximum(dc, 1e-4)[:, None]
    support = smoothstep(dc, 0.01, 0.08)

    Ic = I[ys, xs]
    Bc = B[ys, xs]
    ac = a_nn[ys, xs]
    cc = conf[ys, xs]
    D = Ic - Bc
    Fd = Fh - Bc
    s2 = (Fd * Fd).sum(axis=1)
    s = np.sqrt(s2)
    al = np.clip((D * Fd).sum(axis=1) / (s2 + 1e-4), 0.0, 1.0)
    err = np.sqrt(((D - al[:, None] * Fd) ** 2).sum(axis=1))
    valid = smoothstep(np.maximum(0.045, 0.3 * s) - err, -0.01, 0.01)

    dist = np.sqrt((D * D).sum(axis=1))
    lumI = Ic.mean(axis=1)
    lumB = np.maximum(Bc.mean(axis=1), 1e-3)
    k = lumI / lumB
    chroma = np.sqrt(((Ic / np.maximum(lumI, 1e-3)[:, None] - Bc / lumB[:, None]) ** 2).sum(axis=1))
    shadow = smoothstep(k, 0.35, 0.5) * (1 - smoothstep(k, 0.9, 0.98)) * (1 - smoothstep(chroma, 0.06, 0.12))
    notwall = smoothstep(dist, 0.07, 0.15) * (1 - shadow)

    akb = valid * al + (1 - valid) * np.maximum(ac, notwall)
    # 1) край: альфа по формуле смешивания; объявлять пиксель стеной можно,
    #    только если настоящая стена видна рядом
    w = smoothstep(s, sep[0], sep[1]) * support * strength
    a = ac + w * np.where(akb < ac, cc, 1.0) * (akb - ac)
    # 2) дыры: пиксель явно не цвета стены рядом с фигурой — это человек
    #    (белая футболка, которую сеть сделала полупрозрачной у движущейся руки)
    d_person = np.sqrt(((Ic - Fh) ** 2).sum(axis=1))
    hole = smoothstep(dist, 0.12, 0.22) * (1 - shadow) * smoothstep(dist - d_person, 0.04, 0.12) * strength
    a = np.maximum(a, hole)
    out = a_nn.copy()
    out[ys, xs] = np.clip(a, 0.0, 1.0)
    return out


def choke(a, px=1, soft=0.6):
    """
    Подрезка маски внутрь на px пикселей и мягкий край. Сеть и сглаживание во
    времени делают маску на 1–2 пикселя шире человека; на тёмном новом фоне эти
    пиксели — светлая старая стена, кромка видна. Так же делают кеинг-программы
    (Shrink/Grow с отрицательным значением).
    """
    if px > 0:
        a = cv2.erode(a, _ONES3, iterations=int(px))
    if soft > 0:
        a = cv2.GaussianBlur(a, (0, 0), soft)
    return a


_ELL25 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25))
_ELL7 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
_ONES3 = np.ones((3, 3), np.uint8)


# ============================ ЦВЕТ КРАЯ ============================

def foreground_colors(I, a, plate=None, r1=31, r2=5, q=4):
    """
    Очистка цвета края (Forte, Pitié 2021, «blur fusion»): цвет полупрозрачного
    пикселя — это цвет человека рядом плюс малая поправка, а не деление на альфу.
    Деление раздувает ошибку в 5–10 раз и рисует зелёно-голубой ободок.

    Первый проход с большим радиусом — на уменьшенном кадре (размытые средние
    гладкие), второй — в полном разрешении; оба пишут только пиксели края.
    Радиус 31, а не 91 из статьи: на рилсе 1 широкий радиус брал цвет края
    у светлого лба, и редкие тёмные волосы на макушке получали светлую кромку.
    """
    H, W = a.shape
    band = (a > 0.004) & (a < 0.996)
    ys, xs = np.nonzero(band)
    F = I.copy()
    if len(ys) == 0:
        return F
    w, h = W // q, H // q
    Iq = cv2.resize(I, (w, h), interpolation=cv2.INTER_AREA)
    aq = cv2.resize(a, (w, h), interpolation=cv2.INTER_AREA)
    rq = max(3, (r1 // q) | 1)
    ba = cv2.blur(aq, (rq, rq))
    bF = cv2.blur(Iq * aq[..., None], (rq, rq)) / (ba[..., None] + 1e-5)
    bB = cv2.blur(Iq * (1 - aq)[..., None], (rq, rq)) / ((1 - ba)[..., None] + 1e-5)
    yq, xq = np.minimum(ys // q, h - 1), np.minimum(xs // q, w - 1)
    Ic = I[ys, xs]
    ac = a[ys, xs][:, None]
    bFc, bBc = bF[yq, xq], bB[yq, xq]
    F[ys, xs] = np.clip(bFc + ac * (Ic - ac * bFc - (1 - ac) * bBc), 0, 1)

    B2 = plate if plate is not None else cv2.resize(bB, (W, H), interpolation=cv2.INTER_LINEAR)
    k = (r2, r2)
    ba2 = cv2.blur(a, k)[ys, xs][:, None]
    bF2 = cv2.blur(F * a[..., None], k)[ys, xs] / (ba2 + 1e-5)
    bB2 = cv2.blur(B2 * (1 - a)[..., None], k)[ys, xs] / ((1 - ba2) + 1e-5)
    F[ys, xs] = np.clip(bF2 + ac * (Ic - ac * bF2 - (1 - ac) * bB2), 0, 1)
    return F


# ======================= ДРОЖЬ МАСКИ ВО ВРЕМЕНИ =======================

class ChatterReducer:
    """
    Маска прошлого кадра переносится по оптическому потоку в текущий и
    смешивается с новой. Где перенос не совпал с картинкой (быстрая рука,
    склейка), смешивания нет — шлейфа не будет.
    """

    def __init__(self, W, H, strength=0.55, cut=0.06):
        self.W, self.H = W, H
        self.s = strength
        self.cut = cut
        self.dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_FAST)
        self.prev_g = None
        self.prev_a = None
        self.prev_full_g = None
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.cuts = 0

    def __call__(self, I, a):
        hw, hh = self.W // 2, self.H // 2
        g_full = cv2.cvtColor((I * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
        g = cv2.resize(g_full, (hw, hh), interpolation=cv2.INTER_AREA)
        if self.prev_g is None or self.s <= 0:
            self.prev_g, self.prev_a, self.prev_full_g = g, a, g_full
            return a
        if np.abs(g.astype(np.int16) - self.prev_g.astype(np.int16)).mean() / 255.0 > self.cut:
            self.cuts += 1
            self.prev_g, self.prev_a, self.prev_full_g = g, a, g_full
            return a
        flow = self.dis.calc(g, self.prev_g, None)
        fx = cv2.resize(flow[..., 0], (self.W, self.H), interpolation=cv2.INTER_LINEAR) * 2
        fy = cv2.resize(flow[..., 1], (self.W, self.H), interpolation=cv2.INTER_LINEAR) * 2
        mx, my = self.xx + fx, self.yy + fy
        a_w = cv2.remap(self.prev_a, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        g_w = cv2.remap(self.prev_full_g, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        err = np.abs(g_full.astype(np.float32) - g_w.astype(np.float32)) / 255.0
        err = cv2.GaussianBlur(err, (0, 0), 2.0)
        lam = self.s * np.exp(-err / 0.025)
        out = lam * a_w + (1 - lam) * a
        self.prev_g, self.prev_a, self.prev_full_g = g, out, g_full
        return out.astype(np.float32)


# ============================ ФОН ============================

class Background:
    """
    Кадры нового фона. Видео — с правильной частотой кадров (25 → 30 без ускорения),
    по размеру кадра без растяжения, при нехватке длины — мягкий переход в начало
    вместо рывка. Картинка — с медленным наездом, чтобы фон жил.
    """

    def __init__(self, path, W, H, n_frames, fps=30.0, blur=0.0, slow=1.0, zoom=1.0, dx=0,
                 push=0.04, xfade=1.0, log=print):
        self.W, self.H, self.n, self.fps = W, H, n_frames, fps
        self.blur, self.i = blur, 0
        self.is_video = path.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".mkv"))
        self.log = log
        if not self.is_video:
            from PIL import Image
            im = Image.open(path).convert("RGB")
            sc = max(W / im.width, H / im.height) * zoom * (1 + push)
            im = im.resize((int(im.width * sc + .5), int(im.height * sc + .5)), Image.LANCZOS)
            self.img = np.asarray(im).astype(np.float32) / 255.0
            if blur > 0:
                self.img = cv2.GaussianBlur(self.img, (0, 0), blur)
            self.push, self.zoom, self.dx = push, zoom, dx
            return
        _, _, sfps, dur = probe(path)
        vf = []
        if slow != 1.0:
            vf.append(f"setpts=N/({sfps:.4f}/{slow})/TB")
        if slow != 1.0 or abs(sfps - fps) > 0.01:
            # смешивание соседних кадров вместо дублей: без рывка 25 → 30
            vf.append(f"framerate=fps={fps}")
        vf.append(f"scale={int(W * zoom)}:{int(H * zoom)}:force_original_aspect_ratio=increase:flags=lanczos")
        vf.append(f"crop={W}:{H}:(iw-{W})/2+{dx}:(ih-{H})/2")
        if blur > 0:
            vf.append(f"gblur=sigma={blur}")
        self.vf = ",".join(vf)
        self.path = path
        self.len = int(dur * slow * fps) - 2          # запас: последний кадр бывает недочитан
        self.xf = int(xfade * fps)
        if self.len >= n_frames:
            log(f"фон: видео {dur * slow:.1f} с — хватает на весь ролик, без петли")
        else:
            log(f"фон: видео {dur * slow:.1f} с короче ролика — петля с переходом {xfade:.1f} с")
        self.head = []
        self.proc = reader(path, W, H, vf=self.vf)
        self.pos = 0

    def _read(self):
        fr = read_frame(self.proc, self.W, self.H)
        if fr is None:                        # конец клипа раньше расчёта — начинаем заново
            self.proc = reader(self.path, self.W, self.H, vf=self.vf)
            self.pos = 0
            fr = read_frame(self.proc, self.W, self.H)
        return fr

    def next(self):
        t = self.i / max(self.n - 1, 1)
        self.i += 1
        if not self.is_video:
            h, w = self.img.shape[:2]
            s = 1 + self.push * t                       # медленный наезд
            cw, ch = self.W * (1 + self.push) / s, self.H * (1 + self.push) / s
            cx = w / 2 + self.dx
            cy = h / 2
            M = np.float32([[cw / self.W, 0, cx - cw / 2], [0, ch / self.H, cy - ch / 2]])
            return cv2.warpAffine(self.img, M, (self.W, self.H), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP,
                                  borderMode=cv2.BORDER_REFLECT)
        fr = self._read()
        if self.len < self.n and self.xf > 0:
            if self.pos < self.xf and len(self.head) < self.xf:
                self.head.append(fr)
            loop_at = self.len - self.xf
            if self.pos >= loop_at and self.head:
                k = self.pos - loop_at
                if k < len(self.head):
                    w8 = (k + 1) / (self.xf + 1)
                    fr = fr * (1 - w8) + self.head[k] * w8
                if self.pos == self.len - 1:
                    # продолжаем с кадра после уже показанного перехода
                    self.proc.kill()
                    self.proc = reader(self.path, self.W, self.H, vf=self.vf)
                    for _ in range(self.xf):
                        read_frame(self.proc, self.W, self.H)
                    self.pos = self.xf - 1
        self.pos += 1
        return fr

    def close(self):
        if self.is_video and self.proc:
            self.proc.kill()
