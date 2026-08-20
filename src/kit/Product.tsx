/**
 * Компоненты продающего ролика. Всё, что рассказывает про товар, а не про
 * автора: сравнение до/после, оффер, указатель на деталь, шаги, отзыв, цифра.
 *
 * Тексты приходят из спеки — язык не зашит, армянский рендерится через NotoArm.
 * Эмодзи нет нигде, по тому же правилу, что и в остальном ките.
 */
import { AbsoluteFill, Img, staticFile, useCurrentFrame, interpolate, Easing } from "remotion";
import { Video } from "@remotion/media";
import { useFont, EASE } from "./Kit";
import type { Lang, Style } from "../styles";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const EASE_BACK = Easing.bezier(0.34, 1.56, 0.64, 1);

/**
 * Затухание на выходе. Накладка, которая просто пропадает на последнем кадре
 * своей сцены, читается как сбой сборки — глаз замечает обрыв. Шесть кадров
 * достаточно, чтобы это выглядело намеренным, и мало, чтобы не тормозить темп.
 *
 * `dur` — длительность накладки в кадрах; 0 означает «длительность неизвестна»,
 * тогда выход не анимируется.
 */
const outFade = (frame: number, dur?: number) =>
  dur && dur > 12 ? interpolate(frame, [dur - 6, dur], [1, 0], clamp) : 1;

/* ---------- до / после ---------- */

export type Side = { src: string; isVideo?: boolean; label?: string };

/**
 * Два состояния в одном кадре: «после» открывается поверх «до» движущейся
 * границей. Для геля это главный кадр ролика — пятно есть, пятна нет.
 *
 * `at` — на какой секунде сцены начинается переход, `dur` — сколько едет.
 */
export const BeforeAfter: React.FC<{
  before: Side;
  after: Side;
  style: Style;
  lang: Lang;
  fps?: number;
  at?: number;
  dur?: number;
  /** vertical — граница едет слева направо, horizontal — сверху вниз */
  axis?: "vertical" | "horizontal";
}> = ({ before, after, style, lang, fps = 30, at = 0.6, dur = 0.9, axis = "vertical" }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const t = frame / fps;
  const p = interpolate(t, [at, at + dur], [0, 100], { ...clamp, easing: EASE });

  const media = (s: Side) =>
    s.isVideo ? (
      <Video src={staticFile(s.src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    ) : (
      <Img src={staticFile(s.src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    );

  const clip =
    axis === "vertical"
      ? `inset(0 ${100 - p}% 0 0)`
      : `inset(0 0 ${100 - p}% 0)`;

  const tag = (text: string, side: "left" | "right") => (
    <div
      style={{
        position: "absolute",
        // ниже бейджа бренда: он стоит слева сверху и иначе перекрывает метку
        top: 268,
        [side]: 40,
        fontFamily: font,
        fontWeight: 900,
        fontSize: 34,
        letterSpacing: 1.5,
        color: side === "left" ? style.textOn : style.ink,
        background: side === "left" ? "rgba(0,0,0,.55)" : style.accent,
        padding: "9px 20px",
        borderRadius: 8,
        textTransform: "uppercase",
      }}
    >
      {text}
    </div>
  );

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <AbsoluteFill>{media(before)}</AbsoluteFill>
      <AbsoluteFill style={{ clipPath: clip }}>{media(after)}</AbsoluteFill>

      {/* граница — тонкая линия, а не жирная полоса: полоса выглядит дёшево */}
      {p > 0.5 && p < 99.5 ? (
        <div
          style={
            axis === "vertical"
              ? {
                  position: "absolute",
                  left: `${p}%`,
                  top: 0,
                  width: 4,
                  height: "100%",
                  background: style.accent,
                  boxShadow: `0 0 26px ${style.accent}`,
                }
              : {
                  position: "absolute",
                  top: `${p}%`,
                  left: 0,
                  height: 4,
                  width: "100%",
                  background: style.accent,
                  boxShadow: `0 0 26px ${style.accent}`,
                }
          }
        />
      ) : null}

      {before.label ? tag(before.label, "left") : null}
      {after.label && p > 45 ? tag(after.label, "right") : null}
    </AbsoluteFill>
  );
};

/* ---------- оффер ---------- */

/**
 * Плашка с ценой. Старая цена зачёркнута и уходит вверх, новая приходит
 * снизу — движение читается как «стало дешевле» без единого слова.
 */
export const OfferPlate: React.FC<{
  price: string;
  oldPrice?: string;
  note?: string;
  style: Style;
  lang: Lang;
  bottom?: number;
  dur?: number;
}> = ({ price, oldPrice, note, style, lang, bottom = 620, dur }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const app = interpolate(frame, [0, 12], [0, 1], clamp) * outFade(frame, dur);

  return (
    <div
      style={{
        position: "absolute",
        bottom,
        left: 0,
        width: "100%",
        display: "flex",
        justifyContent: "center",
        opacity: app,
        scale: interpolate(frame, [0, 14], [0.82, 1], { ...clamp, easing: EASE_BACK }),
      }}
    >
      <div
        style={{
          background: style.accent,
          color: style.ink,
          borderRadius: 18,
          padding: "16px 30px",
          display: "flex",
          alignItems: "baseline",
          gap: 16,
          boxShadow: `0 18px 48px ${style.accent}55`,
        }}
      >
        {oldPrice ? (
          <span
            style={{
              fontFamily: font,
              fontWeight: 700,
              fontSize: 38,
              opacity: 0.62,
              textDecoration: "line-through",
              translate: `0px ${interpolate(frame, [10, 22], [0, -6], clamp)}px`,
            }}
          >
            {oldPrice}
          </span>
        ) : null}
        <span
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: 66,
            lineHeight: 1,
            translate: `0px ${interpolate(frame, [8, 22], [14, 0], { ...clamp, easing: EASE })}px`,
          }}
        >
          {price}
        </span>
        {note ? (
          <span style={{ fontFamily: font, fontWeight: 700, fontSize: 28, opacity: 0.8 }}>{note}</span>
        ) : null}
      </div>
    </div>
  );
};

/* ---------- указатель ---------- */

/**
 * Стрелка на деталь кадра. Точка задаётся долями кадра, чтобы не зависеть
 * от разрешения: {x: .62, y: .38} — чуть правее и выше центра.
 */
export const Pointer: React.FC<{
  x: number;
  y: number;
  label?: string;
  style: Style;
  lang: Lang;
  /** откуда приходит стрелка */
  from?: "left" | "right" | "top" | "bottom";
  dur?: number;
}> = ({ x, y, label, style, lang, from = "left", dur }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [0, 14], [0, 1], { ...clamp, easing: EASE });
  const pulse = 1 + Math.sin(frame / 7) * 0.045;
  const out = outFade(frame, dur);

  const len = 190 * grow;
  const horizontal = from === "left" || from === "right";
  const sign = from === "left" || from === "top" ? -1 : 1;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: out }}>
      {/* кольцо на точке интереса */}
      <div
        style={{
          position: "absolute",
          left: `${x * 100}%`,
          top: `${y * 100}%`,
          width: 92,
          height: 92,
          marginLeft: -46,
          marginTop: -46,
          borderRadius: 92,
          border: `4px solid ${style.accent}`,
          opacity: interpolate(frame, [0, 8], [0, 1], clamp),
          scale: pulse,
          boxShadow: `0 0 30px ${style.accent}66`,
        }}
      />
      {/* линия к подписи */}
      <div
        style={{
          position: "absolute",
          left: `${x * 100}%`,
          top: `${y * 100}%`,
          width: horizontal ? len : 4,
          height: horizontal ? 4 : len,
          marginLeft: horizontal ? (sign < 0 ? -len - 46 : 46) : -2,
          marginTop: horizontal ? -2 : sign < 0 ? -len - 46 : 46,
          background: style.accent,
        }}
      />
      {/* Подпись прижимается к краю кадра, а не отсчитывается от конца линии:
          при точке у края длинный текст иначе уезжает за границу и обрезается. */}
      {label ? (
        <div
          style={{
            position: "absolute",
            top: `${y * 100}%`,
            ...(horizontal
              ? sign < 0
                ? { left: 34, marginTop: -26 }
                : { right: 34, marginTop: -26 }
              : { left: 0, width: "100%", display: "flex", justifyContent: "center",
                  marginTop: sign < 0 ? -len - 96 : len + 60 }),
            opacity: interpolate(frame, [10, 20], [0, 1], clamp),
          }}
        >
          <span
            style={{
              display: "inline-block",
              fontFamily: font,
              fontWeight: 900,
              fontSize: 36,
              color: style.ink,
              background: style.accent,
              padding: "8px 18px",
              borderRadius: 8,
              whiteSpace: "nowrap",
            }}
          >
            {label}
          </span>
        </div>
      ) : null}
    </div>
  );
};

/* ---------- шаг ---------- */

/** «Шаг 1» и текст. Для формата польза-гайд и любой инструкции. */
export const StepBadge: React.FC<{
  n: number;
  text?: string;
  style: Style;
  lang: Lang;
  top?: number;
  dur?: number;
}> = ({ n, text, style, lang, top = 240, dur }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 46,
        display: "flex",
        alignItems: "center",
        gap: 18,
        opacity: interpolate(frame, [0, 9], [0, 1], clamp) * outFade(frame, dur),
        translate: `${interpolate(frame, [0, 16], [-26, 0], { ...clamp, easing: EASE })}px 0px`,
      }}
    >
      <div
        style={{
          width: 74,
          height: 74,
          borderRadius: 74,
          background: style.accent,
          color: style.ink,
          fontFamily: font,
          fontWeight: 900,
          fontSize: 42,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {n}
      </div>
      {text ? (
        <div
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: 40,
            color: style.textOn,
            textShadow: "0 3px 16px rgba(0,0,0,.9)",
            maxWidth: 560,
          }}
        >
          {text}
        </div>
      ) : null}
    </div>
  );
};

/* ---------- отзыв ---------- */

/** Цитата покупателя. Приходит из отзывов, а не сочиняется. */
export const QuoteCard: React.FC<{
  text: string;
  author?: string;
  style: Style;
  lang: Lang;
  top?: number;
  dur?: number;
}> = ({ text, author, style, lang, top = 380, dur }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: 56,
        right: 56,
        background: "rgba(0,0,0,.62)",
        borderLeft: `6px solid ${style.accent}`,
        borderRadius: 14,
        padding: "22px 26px",
        opacity: interpolate(frame, [0, 10], [0, 1], clamp) * outFade(frame, dur),
        translate: `0px ${interpolate(frame, [0, 18], [22, 0], { ...clamp, easing: EASE })}px`,
      }}
    >
      <div style={{ fontFamily: font, fontWeight: 700, fontSize: 38, color: style.textOn, lineHeight: 1.3 }}>
        {text}
      </div>
      {author ? (
        <div style={{ fontFamily: font, fontWeight: 700, fontSize: 26, color: style.accent, marginTop: 12 }}>
          {author}
        </div>
      ) : null}
    </div>
  );
};

/* ---------- цифра ---------- */

/**
 * Число, которое набегает до значения. Работает там, где есть измеримый
 * результат: «за 30 секунд», «−87% пятна». Придуманных цифр здесь быть не должно.
 */
export const CountUp: React.FC<{
  to: number;
  suffix?: string;
  label?: string;
  style: Style;
  lang: Lang;
  /** длительность накладки в кадрах — от неё считается и скорость набора */
  dur?: number;
  top?: number;
}> = ({ to, suffix = "", label, style, lang, dur, top = 300 }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  // число набирается за первые две трети показа, остальное время стоит
  const count = dur ? Math.max(Math.round(dur * 0.6), 10) : 26;
  const v = Math.round(interpolate(frame, [0, count], [0, to], { ...clamp, easing: EASE }));
  return (
    <div style={{ position: "absolute", top, width: "100%", textAlign: "center", opacity: outFade(frame, dur) }}>
      <div
        style={{
          fontFamily: font,
          fontWeight: 900,
          fontSize: 148,
          lineHeight: 1,
          color: style.accent,
          WebkitTextStroke: `10px ${style.ink}`,
          paintOrder: "stroke fill",
          scale: interpolate(frame, [0, 12], [0.8, 1], { ...clamp, easing: EASE_BACK }),
        }}
      >
        {v}
        {suffix}
      </div>
      {label ? (
        <div
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: 38,
            color: style.textOn,
            letterSpacing: 1.5,
            textTransform: "uppercase",
            marginTop: 10,
            textShadow: "0 3px 16px rgba(0,0,0,.9)",
            opacity: interpolate(frame, [count - 6, count + 6], [0, 1], clamp),
          }}
        >
          {label}
        </div>
      ) : null}
    </div>
  );
};
