/**
 * Сцена «говорящий со слоями» — главный формат профессиональных вертикальных
 * роликов и основное отличие от прежней сборки.
 *
 * Прежде ритм делался резкой: кадр рубился на куски по 2-3 секунды. Замер
 * чужих работающих роликов показал другое: жёстких склеек там почти нет
 * (reel13 — 5 склеек на 48 секунд, 4534534 — ни одной на 20), а «происходит»
 * что-то каждые полторы секунды. Ритм создают слои, приходящие поверх
 * непрерывного кадра: карточки, списки, цифры, вставки.
 *
 * Отсюда устройство сцены: одно видео говорящего идёт целиком, а сверху
 * по расписанию появляются слои. Когда слой требует места (вставка во весь
 * экран), говорящий не исчезает — он уезжает в окно, круглое или
 * прямоугольное. Связь со зрителем не рвётся.
 */
import React from "react";
import { AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame, interpolate, Easing } from "remotion";
import { Video } from "@remotion/media";
import { getStyle, type Lang, type Style } from "../styles";
import { useFont, EASE, zoomAt, fitFontSize } from "../kit/Kit";

const DESIGN = { w: 720, h: 1280 };
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Форма окна, в которое уезжает говорящий, пока на экране вставка. */
export type PipShape = "rect" | "circle" | "none";

export type Pip = {
  shape?: PipShape;
  /** центр окна в долях кадра; по умолчанию низ по центру для круга, верх для рамки */
  x?: number;
  y?: number;
  /** ширина окна в долях кадра */
  size?: number;
  /** кольцо-индикатор длительности по краю круга — приём из сторис */
  timer?: boolean;
};

export type Layer =
  /**
   * вставка во весь экран: сток, скриншот, кадр фермы. Говорящий уходит в окно.
   * Без `src` под окном лежит фирменная подложка стиля — так освобождается
   * место под графику (сетку, список), и лицо ничем не перекрыто.
   */
  | { kind: "insert"; at: number; dur: number; src?: string; isVideo?: boolean; in?: number; label?: string; pip?: Pip }
  /** карточка с картинкой и подписью — приходит снизу, стоит с наклоном */
  | { kind: "card"; at: number; dur: number; src?: string; isVideo?: boolean; title?: string; note?: string; side?: "left" | "right"; y?: number }
  /** список пунктов, появляющихся по одному */
  | { kind: "list"; at: number; dur: number; items: { text: string; note?: string }[]; y?: number; title?: string }
  /**
   * крупная цифра со счётчиком. `plate` — тёмная подложка: без неё белая
   * цифра пропадает на белой футболке или светлой стене
   */
  | { kind: "stat"; at: number; dur: number; to: number; from?: number; suffix?: string; label?: string; y?: number; plate?: boolean; scale?: number }
  /** слово, уходящее эхом вглубь — усиление без вставок */
  | { kind: "kinetic"; at: number; dur: number; word: string; times?: number; y?: number; plate?: boolean }
  /** сетка точек: столько-то аккаунтов. Растёт от `from` до `to` */
  | { kind: "grid"; at: number; dur: number; from: number; to: number; label?: string; y?: number; cell?: number; cols?: number }
  /** крупный титр поверх кадра */
  | { kind: "title"; at: number; dur: number; line1: string; line2?: string; y?: number };

/**
 * Где в исходнике лицо — центр и размер в долях кадра. Меряет
 * `pipeline/quality.py`. Без этого окно центрируется по середине кадра,
 * а голова у говорящего всегда в верхней трети — и в круг попадает
 * половина лица. Так было в первой сборке, владелец поймал сразу.
 */
export type Face = { x: number; y: number; w: number; h: number };

export type TalkScene = {
  type: "talk";
  src: string;
  /** с какой секунды исходника идёт кусок */
  in?: number;
  sec?: number;
  dur?: number;
  volume?: number;
  layers?: Layer[];
  zooms?: [number, number][];
  captions?: boolean;
  face?: Face;
};

/* ---------- вспомогательное ---------- */

/** Плавное появление и уход слоя: 8 кадров на вход, 6 на выход. */
const fade = (frame: number, durF: number, inF = 8, outF = 6) =>
  Math.min(
    interpolate(frame, [0, inF], [0, 1], { ...clamp, easing: EASE }),
    interpolate(frame, [durF - outF, durF], [1, 0], clamp),
  );

/** Выезд снизу вместе с появлением — базовое движение всех слоёв. */
const rise = (frame: number, inF = 10, px = 28) =>
  interpolate(frame, [0, inF], [px, 0], { ...clamp, easing: EASE });

/**
 * Светлый стиль — тёмный текст на светлом. Слои писались под тёмные стили,
 * и на «Светлом разборе» белая подпись сетки пропала на светлой подложке.
 */
const isLight = (st: Style) => st.textOn.toLowerCase() !== "#ffffff";
const plateBg = (st: Style) => (isLight(st) ? "rgba(255,255,255,.92)" : "rgba(8,10,11,.66)");
const ink = (st: Style) => (isLight(st) ? st.textOn : "#fff");

const fmt = (n: number) => Math.round(n).toLocaleString("ru-RU").replace(/,/g, " ");

/* ---------- окно говорящего ---------- */

/**
 * Пока активна вставка, кадр говорящего живёт в окне. Размер и положение
 * считаются в координатах макета, а не в процентах: иначе круг перестаёт
 * быть кругом при смене формата вывода.
 */
const pipBox = (pip: Pip) => {
  const shape = pip.shape ?? "circle";
  const size = (pip.size ?? (shape === "circle" ? 0.42 : 0.46)) * DESIGN.w;
  const h = shape === "circle" ? size : size * (4 / 3);
  const cx = (pip.x ?? 0.5) * DESIGN.w;
  const cy = (pip.y ?? (shape === "circle" ? 0.68 : 0.27)) * DESIGN.h;
  return { left: cx - size / 2, top: cy - h / 2, w: size, h, shape };
};

const clampNum = (v: number, lo: number, hi: number) => Math.min(Math.max(v, lo), hi);

/**
 * Где лежит кадр говорящего внутри окна. Правило: лицо занимает около 40%
 * высоты окна и стоит чуть выше центра — видна вся голова и плечи.
 *
 * Если для этого кадр надо уменьшить сильнее, чем позволяет окно (исходник
 * снят крупно), под ним кладётся размытая копия того же видео, а края
 * резкого кадра растушёвываются. Небольшую разницу, до 15%, не лечим
 * размытием: чистое заполнение окна выглядит лучше лишнего слоя.
 */
const frameInWindow = (box: { w: number; h: number }, face?: Face) => {
  const ratio = DESIGN.w / DESIGN.h;
  const coverH = Math.max(box.h, box.w / ratio);
  if (!face) {
    // без замера — голова говорящего почти всегда в верхней трети кадра
    const h = coverH;
    const w = h * ratio;
    return { w, h, x: (box.w - w) / 2, y: clampNum(box.h * 0.5 - 0.33 * h, box.h - h, 0), fill: false };
  }
  const want = (0.4 * box.h) / face.h;
  const fill = want < coverH * 0.85;
  const h = fill ? Math.max(want, coverH * 0.6) : Math.max(want, coverH);
  const w = h * ratio;
  const x = box.w / 2 - face.x * w;
  const y = box.h * 0.46 - face.y * h;
  return {
    w,
    h,
    fill,
    x: fill ? x : clampNum(x, box.w - w, 0),
    y: fill ? y : clampNum(y, box.h - h, 0),
  };
};

/** Кольцо-индикатор длительности по краю круга — как в сторис. */
const TimerRing: React.FC<{ d: number; progress: number; color: string; color2: string }> = ({
  d,
  progress,
  color,
  color2,
}) => {
  const r = d / 2 - 5;
  const len = 2 * Math.PI * r;
  return (
    <svg width={d} height={d} style={{ position: "absolute", left: 0, top: 0, transform: "rotate(-90deg)" }}>
      <defs>
        <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={color} />
          <stop offset="100%" stopColor={color2} />
        </linearGradient>
      </defs>
      <circle cx={d / 2} cy={d / 2} r={r} stroke="rgba(255,255,255,.18)" strokeWidth={5} fill="none" />
      <circle
        cx={d / 2}
        cy={d / 2}
        r={r}
        stroke="url(#ring)"
        strokeWidth={5}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={len}
        strokeDashoffset={len * (1 - progress)}
      />
    </svg>
  );
};

/* ---------- слои ---------- */

const CardLayer: React.FC<{ l: Extract<Layer, { kind: "card" }>; st: Style; font: string; fps: number; durF: number }> = ({
  l,
  st,
  font,
  fps,
  durF,
}) => {
  const frame = useCurrentFrame();
  const o = fade(frame, durF);
  const tilt = l.side === "left" ? -3.5 : 3.5;
  const x = (l.side === "left" ? -1 : 1) * 46;
  return (
    <div
      style={{
        position: "absolute",
        left: DESIGN.w / 2 - 150 + x,
        top: (l.y ?? 0.56) * DESIGN.h,
        width: 300,
        opacity: o,
        transform: `translateY(${rise(frame)}px) rotate(${tilt}deg)`,
        borderRadius: 18,
        overflow: "hidden",
        background: "#fff",
        boxShadow: "0 18px 40px rgba(0,0,0,.45)",
        padding: 8,
      }}
    >
      {l.src ? (
        l.isVideo ? (
          <Video src={staticFile(l.src)} volume={0} style={{ width: "100%", height: 200, objectFit: "cover", borderRadius: 12 }} />
        ) : (
          <Img src={staticFile(l.src)} style={{ width: "100%", height: 200, objectFit: "cover", borderRadius: 12 }} />
        )
      ) : null}
      {l.title ? (
        <div style={{ fontFamily: font, fontWeight: 900, fontSize: 25, color: "#111", padding: "10px 8px 2px" }}>{l.title}</div>
      ) : null}
      {l.note ? (
        <div style={{ fontFamily: font, fontSize: 19, color: "#666", padding: "0 8px 8px" }}>{l.note}</div>
      ) : null}
    </div>
  );
};

const ListLayer: React.FC<{ l: Extract<Layer, { kind: "list" }>; st: Style; font: string; fps: number; durF: number }> = ({
  l,
  st,
  font,
  fps,
  durF,
}) => {
  const frame = useCurrentFrame();
  const o = fade(frame, durF);
  const step = Math.round(fps * 0.32); // пункты приходят по одному, а не пачкой
  return (
    <div style={{ position: "absolute", left: 60, top: (l.y ?? 0.5) * DESIGN.h, width: DESIGN.w - 120, opacity: o }}>
      {l.title ? (
        <div style={{ fontFamily: font, fontWeight: 900, fontSize: 26, color: st.accent, marginBottom: 12, letterSpacing: 1 }}>
          {l.title}
        </div>
      ) : null}
      {l.items.map((it, i) => {
        const f = frame - i * step;
        const io = interpolate(f, [0, 9], [0, 1], { ...clamp, easing: EASE });
        return (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              background: isLight(st) ? "rgba(255,255,255,.94)" : "rgba(18,18,20,.82)",
              border: `1px solid ${st.accent}44`,
              borderRadius: 14,
              padding: "14px 18px",
              marginBottom: 10,
              opacity: io,
              transform: `translateX(${interpolate(f, [0, 9], [-26, 0], { ...clamp, easing: EASE })}px)`,
            }}
          >
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: 10,
                background: st.accent,
                boxShadow: `0 0 14px ${st.accent}`,
                flexShrink: 0,
              }}
            />
            <div style={{ fontFamily: font, fontWeight: 800, fontSize: 27, color: ink(st) }}>{it.text}</div>
            {it.note ? <div style={{ fontFamily: font, fontSize: 21, color: st.accent, marginLeft: "auto" }}>{it.note}</div> : null}
          </div>
        );
      })}
    </div>
  );
};

const StatLayer: React.FC<{ l: Extract<Layer, { kind: "stat" }>; st: Style; font: string; fps: number; durF: number }> = ({
  l,
  st,
  font,
  fps,
  durF,
}) => {
  const frame = useCurrentFrame();
  const o = fade(frame, durF);
  // счётчик набирает число за две трети показа и стоит до конца — иначе
  // зритель не успевает прочитать итог
  const p = interpolate(frame, [0, durF * 0.66], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const v = (l.from ?? 0) + ((l.to ?? 0) - (l.from ?? 0)) * p;
  // масштаб — когда цифра делит полосу между лицом и субтитрами
  const k = l.scale ?? 1;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: (l.y ?? 0.3) * DESIGN.h,
        textAlign: "center",
        opacity: o,
        transform: `translateY(${rise(frame, 10, 20)}px)`,
      }}
    >
      <div
        style={{
          display: "inline-block",
          padding: l.plate === false ? 0 : `${14 * k}px ${34 * k}px ${16 * k}px`,
          borderRadius: 26,
          background: l.plate === false ? "transparent" : plateBg(st),
          border: l.plate === false ? "none" : `1px solid ${st.accent}33`,
        }}
      >
        <div
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: 118 * k,
            lineHeight: 1,
            color: ink(st),
            textShadow: isLight(st) ? "none" : `0 0 30px ${st.accent}77, 0 6px 22px rgba(0,0,0,.6)`,
          }}
        >
          {fmt(v)}
          {l.suffix ? <span style={{ fontSize: 56 * k, color: st.accent }}>{l.suffix}</span> : null}
        </div>
        {l.label ? (
          <div style={{ fontFamily: font, fontWeight: 800, fontSize: 30 * Math.max(k, 0.85), color: st.accent, letterSpacing: 2, marginTop: 6 * k }}>
            {l.label}
          </div>
        ) : null}
      </div>
    </div>
  );
};

const KineticLayer: React.FC<{ l: Extract<Layer, { kind: "kinetic" }>; st: Style; font: string; fps: number; durF: number }> = ({
  l,
  st,
  font,
  fps,
  durF,
}) => {
  const frame = useCurrentFrame();
  const n = l.times ?? 3;
  const step = Math.round(fps * 0.14);
  const band = fade(frame, durF, 6, 6);
  // длинное армянское слово шире кадра на 78 пунктах — подгоняем по ширине,
  // а строки эха ставим стопкой: наложенные строки читаются как брак, а не приём
  const size = fitFontSize(l.word, font, 900, 78, DESIGN.w - 70, 30);
  const lineH = size * 1.02;
  return (
    <div style={{ position: "absolute", left: 0, right: 0, top: (l.y ?? 0.34) * DESIGN.h, textAlign: "center" }}>
      {l.plate === false ? null : (
        // тёмная полоса во всю ширину: эхо светлым шрифтом на светлой одежде не читается
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: -18,
            height: lineH * n + 36,
            background: isLight(st)
              ? "linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,.88) 18%, rgba(255,255,255,.88) 82%, rgba(255,255,255,0) 100%)"
              : "linear-gradient(90deg, rgba(8,10,11,0) 0%, rgba(8,10,11,.72) 18%, rgba(8,10,11,.72) 82%, rgba(8,10,11,0) 100%)",
            opacity: band,
          }}
        />
      )}
      {Array.from({ length: n }).map((_, i) => {
        const f = frame - i * step;
        const o = Math.min(
          interpolate(f, [0, 6], [0, 1 - i * 0.26], clamp),
          interpolate(frame, [durF - 6, durF], [1, 0], clamp),
        );
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              fontFamily: font,
              fontWeight: 900,
              fontSize: size,
              lineHeight: `${lineH}px`,
              color: i === 1 ? st.accent : ink(st),
              opacity: Math.max(o, 0),
              transform: `translateY(${i * lineH}px) scale(${1 - Math.abs(i - 1) * 0.06})`,
              letterSpacing: 1,
            }}
          >
            {l.word}
          </div>
        );
      })}
    </div>
  );
};

/**
 * Сетка аккаунтов. Показывает то, что словами объясняется долго: было три
 * точки — стало сорок. Точки зажигаются по одной, последние досыпаются
 * пачкой, иначе на сотне аккаунтов анимация не укладывается в бит.
 */
const GridLayer: React.FC<{ l: Extract<Layer, { kind: "grid" }>; st: Style; font: string; fps: number; durF: number }> = ({
  l,
  st,
  font,
  fps,
  durF,
}) => {
  const frame = useCurrentFrame();
  const o = fade(frame, durF);
  const p = interpolate(frame, [0, durF * 0.7], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  const shown = Math.round(l.from + (l.to - l.from) * p);
  // широкая сетка в несколько рядов, когда по высоте её зажимают лицо и субтитры
  const cols = l.cols ?? (l.to > 60 ? 10 : l.to > 24 ? 8 : 5);
  // размер клетки задаётся, когда сетка делит экран с окном говорящего
  const cell = l.cell ?? (l.to > 60 ? 34 : 44);
  const rows = Math.ceil(l.to / cols);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: (l.y ?? 0.28) * DESIGN.h,
        opacity: o,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 14,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${cols}, ${cell}px)`,
          gridTemplateRows: `repeat(${rows}, ${cell * 1.5}px)`,
          gap: 8,
        }}
      >
        {Array.from({ length: l.to }).map((_, i) => {
          const on = i < shown;
          return (
            <div
              key={i}
              style={{
                width: cell,
                height: cell * 1.5,
                borderRadius: 7,
                background: on ? `${st.accent}22` : isLight(st) ? "rgba(16,19,26,.04)" : "rgba(255,255,255,.05)",
                border: `1.5px solid ${on ? st.accent : isLight(st) ? "rgba(16,19,26,.14)" : "rgba(255,255,255,.12)"}`,
                boxShadow: on ? `0 0 12px ${st.accent}55` : "none",
                transform: `scale(${on ? 1 : 0.86})`,
              }}
            />
          );
        })}
      </div>
      <div style={{ fontFamily: font, fontWeight: 900, fontSize: 40, color: ink(st) }}>
        {fmt(shown)}
        {l.label ? <span style={{ fontSize: 26, color: st.accent, marginLeft: 10 }}>{l.label}</span> : null}
      </div>
    </div>
  );
};

const TitleLayer: React.FC<{ l: Extract<Layer, { kind: "title" }>; st: Style; font: string; durF: number }> = ({
  l,
  st,
  font,
  durF,
}) => {
  const frame = useCurrentFrame();
  const o = fade(frame, durF);
  return (
    <div
      style={{
        position: "absolute",
        left: 40,
        right: 40,
        top: (l.y ?? 0.16) * DESIGN.h,
        textAlign: "center",
        opacity: o,
        transform: `translateY(${rise(frame, 9, 22)}px)`,
      }}
    >
      <div style={{ fontFamily: font, fontWeight: 900, fontSize: 68, lineHeight: 1.06, color: ink(st), textShadow: isLight(st) ? "none" : "0 6px 26px rgba(0,0,0,.6)" }}>
        {l.line1}
      </div>
      {l.line2 ? (
        <div style={{ fontFamily: font, fontWeight: 900, fontSize: 68, lineHeight: 1.06, color: st.accent, textShadow: "0 6px 26px rgba(0,0,0,.6)" }}>
          {l.line2}
        </div>
      ) : null}
    </div>
  );
};

/* ---------- сама сцена ---------- */

export const Talk: React.FC<{
  sc: TalkScene;
  styleId?: string;
  lang?: Lang;
  fps: number;
  durF: number;
}> = ({ sc, styleId, lang = "hy", fps, durF }) => {
  const st = getStyle(styleId);
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const layers = sc.layers ?? [];

  // активная вставка на этом кадре: она решает, уезжает ли говорящий в окно
  const active = layers.find(
    (l): l is Extract<Layer, { kind: "insert" }> =>
      l.kind === "insert" && frame >= l.at * fps && frame < (l.at + l.dur) * fps && (l.pip?.shape ?? "circle") !== "none",
  );

  // Две вставки встык с окном одной формы — окно не должно раскрываться
  // во весь экран между ними и схлопываться обратно: это мигание, а не монтаж
  const shapeOf = (l: Extract<Layer, { kind: "insert" }>) => l.pip?.shape ?? "circle";
  const joined = (a: Extract<Layer, { kind: "insert" }>, edge: "in" | "out") =>
    layers.some(
      (o) =>
        o.kind === "insert" &&
        o !== a &&
        shapeOf(o) === shapeOf(a) &&
        (edge === "in"
          ? Math.abs((o.at + o.dur - a.at) * fps) < 3
          : Math.abs((a.at + a.dur - o.at) * fps) < 3),
    );

  const t = active
    ? Math.min(
        joined(active, "in") ? 1 : interpolate(frame - active.at * fps, [0, 10], [0, 1], { ...clamp, easing: EASE }),
        joined(active, "out")
          ? 1
          : interpolate(frame - active.at * fps, [active.dur * fps - 8, active.dur * fps], [1, 0], clamp),
      )
    : 0;

  // наезды по смыслу работают, пока говорящий на весь экран; в окне кадр стоит
  const zoom = zoomAt(frame, sc.zooms ?? [[0, 1]], fps, st.motion.zoomFrames);
  const zoomNow = interpolate(t, [0, 1], [zoom, 1]);
  const origin = sc.face ? `${sc.face.x * 100}% ${sc.face.y * 100}%` : "50% 35%";

  const box = active ? pipBox(active.pip ?? {}) : null;
  const ring = active?.pip?.timer && box?.shape === "circle";
  const ringP = active ? (frame - active.at * fps) / (active.dur * fps) : 0;

  // геометрия окна: полный экран → окно
  const left = box ? interpolate(t, [0, 1], [0, box.left]) : 0;
  const top = box ? interpolate(t, [0, 1], [0, box.top]) : 0;
  const w = box ? interpolate(t, [0, 1], [DESIGN.w, box.w]) : DESIGN.w;
  const h = box ? interpolate(t, [0, 1], [DESIGN.h, box.h]) : DESIGN.h;
  const radius = box ? interpolate(t, [0, 1], [0, box.shape === "circle" ? box.w / 2 : 26]) : 0;

  // геометрия кадра внутри окна: весь кадр → наведение на лицо
  const inner = box ? frameInWindow(box, sc.face) : null;
  const vw = inner ? interpolate(t, [0, 1], [DESIGN.w, inner.w]) : DESIGN.w;
  const vh = inner ? interpolate(t, [0, 1], [DESIGN.h, inner.h]) : DESIGN.h;
  const vx = inner ? interpolate(t, [0, 1], [0, inner.x]) : 0;
  const vy = inner ? interpolate(t, [0, 1], [0, inner.y]) : 0;
  const trimBefore = sc.in ? Math.round(sc.in * fps) : undefined;

  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      {/* вставки лежат под говорящим: он всегда сверху, иначе окно перекроется */}
      {layers.map((l, i) =>
        l.kind === "insert" ? (
          <Sequence key={`i${i}`} from={Math.round(l.at * fps)} durationInFrames={Math.round(l.dur * fps)} layout="none">
            <InsertBody
              l={l}
              fps={fps}
              durF={Math.round(l.dur * fps)}
              st={st}
              font={font}
              joinIn={joined(l, "in")}
              joinOut={joined(l, "out")}
            />
          </Sequence>
        ) : null,
      )}

      <div
        style={{
          position: "absolute",
          left,
          top,
          width: w,
          height: h,
          borderRadius: radius,
          overflow: "hidden",
          border: t > 0.05 ? `${interpolate(t, [0, 1], [0, 4])}px solid ${st.accent}` : "none",
          boxShadow: t > 0.05 ? `0 16px 46px rgba(0,0,0,${0.5 * t})` : "none",
        }}
      >
        {inner?.fill && t > 0.02 ? (
          // размытая подложка — только когда резкий кадр меньше окна
          <Video
            src={staticFile(sc.src)}
            trimBefore={trimBefore}
            volume={0}
            objectFit="cover"
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", filter: "blur(14px) brightness(.8)", scale: 1.15 }}
          />
        ) : null}
        <Video
          src={staticFile(sc.src)}
          trimBefore={trimBefore}
          volume={sc.volume ?? 1}
          objectFit="cover"
          style={{
            position: "absolute",
            left: vx,
            top: vy,
            width: vw,
            height: vh,
            scale: zoomNow,
            transformOrigin: origin,
            maskImage: inner?.fill
              ? "linear-gradient(to right, transparent 0, #000 9%, #000 91%, transparent 100%)"
              : undefined,
          }}
        />
      </div>

      {ring && box ? (
        <div style={{ position: "absolute", left: box.left, top: box.top, width: box.w, height: box.h, opacity: t }}>
          <TimerRing d={box.w} progress={Math.min(Math.max(ringP, 0), 1)} color={st.accent} color2={st.accent2} />
        </div>
      ) : null}

      {/* остальные слои — поверх говорящего */}
      {layers.map((l, i) => {
        if (l.kind === "insert") return null;
        const from = Math.round(l.at * fps);
        const dF = Math.round(l.dur * fps);
        return (
          <Sequence key={`l${i}`} from={from} durationInFrames={dF} layout="none">
            {l.kind === "card" ? (
              <CardLayer l={l} st={st} font={font} fps={fps} durF={dF} />
            ) : l.kind === "list" ? (
              <ListLayer l={l} st={st} font={font} fps={fps} durF={dF} />
            ) : l.kind === "stat" ? (
              <StatLayer l={l} st={st} font={font} fps={fps} durF={dF} />
            ) : l.kind === "kinetic" ? (
              <KineticLayer l={l} st={st} font={font} fps={fps} durF={dF} />
            ) : l.kind === "grid" ? (
              <GridLayer l={l} st={st} font={font} fps={fps} durF={dF} />
            ) : (
              <TitleLayer l={l} st={st} font={font} durF={dF} />
            )}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

/**
 * Фирменная подложка стиля — когда говорящий уходит в окно ради графики.
 * Не плоская заливка: мягкий свет акцентом и едва видная сетка дают глубину,
 * иначе окно висит в пустоте.
 */
const Backdrop: React.FC<{ st: Style }> = ({ st }) => {
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 600], [0, 26]);
  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse 70% 45% at 50% 30%, ${st.accent}22, transparent 70%),
                       radial-gradient(ellipse 60% 40% at 50% 85%, ${st.accent2}18, transparent 70%)`,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage: `linear-gradient(${st.textOff} 1px, transparent 1px), linear-gradient(90deg, ${st.textOff} 1px, transparent 1px)`,
          backgroundSize: "48px 48px",
          backgroundPosition: `0 ${drift}px`,
          opacity: 0.12,
        }}
      />
    </AbsoluteFill>
  );
};

/** Тело вставки: видео или картинка на весь кадр с медленным наездом. */
const InsertBody: React.FC<{
  l: Extract<Layer, { kind: "insert" }>;
  fps: number;
  durF: number;
  st: Style;
  font: string;
  joinIn?: boolean;
  joinOut?: boolean;
}> = ({ l, fps, durF, st, font, joinIn, joinOut }) => {
  const frame = useCurrentFrame();
  const s = interpolate(frame, [0, durF], [1.02, 1.1]); // статичная вставка читается как зависший кадр
  const o = Math.min(
    joinIn ? 1 : interpolate(frame, [0, 7], [0, 1], { ...clamp, easing: EASE }),
    joinOut ? 1 : interpolate(frame, [durF - 6, durF], [1, 0], clamp),
  );
  return (
    <AbsoluteFill style={{ opacity: o, background: st.ink }}>
      {!l.src ? (
        <Backdrop st={st} />
      ) : l.isVideo ?? true ? (
        <Video
          src={staticFile(l.src)}
          trimBefore={l.in ? Math.round(l.in * fps) : undefined}
          volume={0}
          objectFit="cover"
          style={{ width: "100%", height: "100%", scale: s }}
        />
      ) : (
        <Img src={staticFile(l.src)} style={{ width: "100%", height: "100%", objectFit: "cover", scale: s }} />
      )}
      {l.label ? (
        <div
          style={{
            position: "absolute",
            top: 150,
            left: 34,
            fontFamily: font,
            fontWeight: 900,
            fontSize: 24,
            letterSpacing: 2,
            color: st.ink,
            background: st.accent,
            padding: "7px 16px",
            borderRadius: 6,
          }}
        >
          {l.label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
