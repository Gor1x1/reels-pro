/**
 * Набор компонентов монтажа. Все берут внешний вид из стиля (styles.ts),
 * поэтому один и тот же ролик собирается в любом стиле без правок кода.
 * Эмодзи не используются — по умолчанию они выключены в стилях.
 */
import {
  AbsoluteFill,
  Img,
  staticFile,
  useCurrentFrame,
  interpolate,
  Easing,
  random,
  delayRender,
  continueRender,
} from "remotion";
import { useEffect, useState } from "react";
import { FONT_FOR, type Lang, type Style } from "../styles";

export const EASE = Easing.bezier(0.16, 1, 0.3, 1);

/* ---------- шрифты ---------- */
export const useFont = (lang: Lang = "ru") => {
  const [, set] = useState(0);
  useEffect(() => {
    const { file, family, weight } = FONT_FOR[lang];
    const h = delayRender(`font-${family}`);
    const f = new FontFace(family, `url(${staticFile(file)})`, weight ? { weight: `${weight}` } : {});
    f.load()
      .then((l) => {
        document.fonts.add(l);
        set((x) => x + 1);
        continueRender(h);
      })
      .catch(() => {
        set((x) => x + 1);
        continueRender(h);
      });
  }, [lang]);
  return `${FONT_FOR[lang].family}, Arial Black, Arial, sans-serif`;
};

/* ---------- фон: боке ---------- */
export const Bokeh: React.FC<{ style: Style }> = ({ style }) => {
  const frame = useCurrentFrame();
  if (!style.decor.bokeh) return null;
  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none" }}>
      {new Array(style.decor.bokeh).fill(0).map((_, i) => {
        const sx = random(`x${i}`);
        const sy = random(`y${i}`);
        const ss = random(`s${i}`);
        const size = 3 + ss * 10;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${sx * 100}%`,
              top: `${(((sy * 100 - frame * 0.035 * (0.4 + ss)) % 110) + 110) % 110}%`,
              width: size,
              height: size,
              borderRadius: size,
              background: style.accent,
              opacity: 0.1 + ss * 0.3,
              filter: `blur(${1 + ss * 2}px)`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/* ---------- виньетка ---------- */
export const Vignette: React.FC<{ style: Style }> = ({ style }) =>
  style.decor.vignette ? (
    <AbsoluteFill
      style={{
        pointerEvents: "none",
        background: `radial-gradient(ellipse at 50% 45%, transparent 45%, rgba(0,0,0,${style.decor.vignette}) 100%)`,
      }}
    />
  ) : null;

/* ---------- субтитры ---------- */
export type KWord = { t: string; s: number; e: number };
export type KBlock = { start: number; end: number; words: KWord[] };

export const Captions: React.FC<{
  blocks: KBlock[];
  style: Style;
  lang: Lang;
  fps?: number;
}> = ({ blocks, style, lang, fps = 30 }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const t = frame / fps;
  const c = style.caption;
  const b = blocks.find((x) => t >= x.start - 0.08 && t <= x.end + 0.22);
  if (!b) return null;
  const local = (t - b.start) * fps;

  const body = (
    <span
      style={{
        fontFamily: font,
        fontWeight: 900,
        fontSize: c.fontSize,
        lineHeight: 1.24,
        textAlign: c.align,
        display: "block",
        textTransform: c.uppercase ? "uppercase" : "none",
      }}
    >
      {b.words.map((w, i) => {
        const spoken = t >= w.s - 0.02;
        const dim = c.kind === "karaoke" && !spoken;
        return (
          <span
            key={i}
            style={{
              color: dim ? style.textOff : style.textOn,
              marginRight: 10,
              display: "inline-block",
              WebkitTextStroke: c.stroke ? `${c.stroke}px ${style.ink}` : undefined,
              paintOrder: "stroke fill",
              textShadow: c.plate ? undefined : `0 3px 0 ${style.ink}, 0 0 20px rgba(0,0,0,.85)`,
              scale:
                c.kind === "punch" && spoken
                  ? interpolate(t - w.s, [0, 0.12], [style.motion.captionPopScale, 1], {
                      extrapolateRight: "clamp",
                      extrapolateLeft: "clamp",
                      easing: EASE,
                    })
                  : 1,
            }}
          >
            {w.t}
          </span>
        );
      })}
    </span>
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: c.bottom,
        left: 0,
        width: "100%",
        display: "flex",
        justifyContent: c.align === "center" ? "center" : "flex-start",
        paddingLeft: c.align === "center" ? 0 : 44,
        paddingRight: 44,
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          maxWidth: c.maxWidth,
          background: c.plate ?? "transparent",
          borderRadius: c.radius,
          padding: c.plate ? "10px 18px" : 0,
          opacity: interpolate(local, [0, 4], [0, 1], {
            extrapolateRight: "clamp",
            extrapolateLeft: "clamp",
          }),
          scale: interpolate(local, [0, 6], [style.motion.captionPopScale, 1], {
            extrapolateRight: "clamp",
            extrapolateLeft: "clamp",
            easing: EASE,
          }),
        }}
      >
        {body}
      </div>
    </div>
  );
};

/* ---------- акцентный титр ---------- */
export const Punch: React.FC<{
  line1: string;
  line2?: string;
  style: Style;
  lang: Lang;
}> = ({ line1, line2, style, lang }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const p = style.punch;

  const row = (text: string, color: string, delay: number) => (
    <div style={{ display: "flex", justifyContent: "center", gap: "0 14px", flexWrap: "wrap" }}>
      {text.split(" ").map((w, i) => (
        <span
          key={i}
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: p.fontSize,
            lineHeight: 1.02,
            color,
            textTransform: "uppercase",
            WebkitTextStroke: p.stroke ? `${p.stroke}px ${style.ink}` : undefined,
            paintOrder: "stroke fill",
            textShadow: p.stroke ? "0 5px 0 rgba(0,0,0,.55)" : "0 3px 18px rgba(0,0,0,.8)",
            opacity: interpolate(frame - delay - i * 3, [0, 5], [0, 1], {
              extrapolateRight: "clamp",
              extrapolateLeft: "clamp",
            }),
            scale: interpolate(frame - delay - i * 3, [0, 9], [0.66, 1], {
              extrapolateRight: "clamp",
              extrapolateLeft: "clamp",
              easing: EASE,
            }),
          }}
        >
          {w}
        </span>
      ))}
    </div>
  );

  return (
    <div style={{ position: "absolute", top: p.top, left: 0, width: "100%", padding: "0 26px", boxSizing: "border-box" }}>
      {row(line1, style.textOn, 0)}
      {line2 ? row(line2, p.twoTone ? style.accent : style.textOn, 4) : null}
      {p.underline ? (
        <div
          style={{
            height: 6,
            borderRadius: 3,
            background: style.accent,
            margin: "12px auto 0",
            width: interpolate(frame, [8, 22], [0, 280], {
              extrapolateRight: "clamp",
              extrapolateLeft: "clamp",
              easing: EASE,
            }),
          }}
        />
      ) : null}
    </div>
  );
};

/* ---------- уголки-скобки ---------- */
export const Brackets: React.FC<{ style: Style; inset?: number; arm?: number; top?: number; bottom?: number }> = ({
  style,
  inset = 30,
  arm = 74,
  top = 230,
  bottom = 290,
}) => {
  const frame = useCurrentFrame();
  if (!style.decor.brackets) return null;
  const th = 6;
  const g = interpolate(frame, [0, 16], [0, arm], { extrapolateRight: "clamp", easing: EASE });
  const c = (l: string, t: string, hx: number, vy: number) => (
    <>
      <div style={{ position: "absolute", left: l, top: t, width: g, height: th, background: style.accent, transformOrigin: hx > 0 ? "left" : "right", scale: `${hx} 1` }} />
      <div style={{ position: "absolute", left: l, top: t, width: th, height: g, background: style.accent, transformOrigin: vy > 0 ? "top" : "bottom", scale: `1 ${vy}` }} />
    </>
  );
  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      {c(`${inset}px`, `${top}px`, 1, 1)}
      {c(`calc(100% - ${inset + th}px)`, `${top}px`, -1, 1)}
      {c(`${inset}px`, `calc(100% - ${bottom}px)`, 1, -1)}
      {c(`calc(100% - ${inset + th}px)`, `calc(100% - ${bottom}px)`, -1, -1)}
    </div>
  );
};

/* ---------- прогресс-бар ---------- */
export const Progress: React.FC<{ style: Style; total: number }> = ({ style, total }) => {
  const frame = useCurrentFrame();
  if (!style.decor.progressBar) return null;
  return (
    <div style={{ position: "absolute", top: 0, left: 0, height: 6, width: "100%", background: "rgba(255,255,255,.13)" }}>
      <div
        style={{
          height: 6,
          width: `${interpolate(frame, [0, total], [0, 100], { extrapolateRight: "clamp" })}%`,
          background: `linear-gradient(90deg, ${style.accent}, ${style.accent2})`,
        }}
      />
    </div>
  );
};

/* ---------- бейдж бренда ---------- */
export const Badge: React.FC<{ style: Style; text?: string; src?: string; lang?: Lang; size?: number }> = ({
  style,
  text = "GTH",
  src,
  lang = "en",
  size = 86,
}) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  if (!style.decor.badge) return null;
  const spin = interpolate(frame, [0, 260], [0, 360]);
  return (
    <div style={{ position: "absolute", right: 24, bottom: 150, width: size, height: size, opacity: interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" }) }}>
      <svg width={size} height={size} style={{ position: "absolute", rotate: `${spin}deg` }}>
        <circle cx={size / 2} cy={size / 2} r={size / 2 - 3} fill="none" stroke={style.accent} strokeWidth={3} strokeDasharray="10 7" />
      </svg>
      <div
        style={{
          position: "absolute",
          left: 7,
          top: 7,
          width: size - 14,
          height: size - 14,
          borderRadius: size,
          overflow: "hidden",
          background: style.ink,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {src ? (
          <Img src={staticFile(src)} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <span style={{ fontFamily: font, fontWeight: 900, fontSize: size * 0.28, color: "#fff" }}>{text}</span>
        )}
      </div>
    </div>
  );
};

/* ---------- титр с именем ---------- */
export const NameTitle: React.FC<{ name: string; role?: string; style: Style; lang: Lang; dur: number }> = ({
  name,
  role,
  style,
  lang,
  dur,
}) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const w = interpolate(frame, [4, 20], [0, 1], { extrapolateRight: "clamp", easing: EASE });
  return (
    <div
      style={{
        position: "absolute",
        left: 46,
        bottom: 430,
        opacity: interpolate(frame, [0, 8, dur - 12, dur], [0, 1, 1, 0], {
          extrapolateRight: "clamp",
          extrapolateLeft: "clamp",
        }),
        translate: interpolate(frame, [0, 16], ["-34px 0px", "0px 0px"], {
          extrapolateRight: "clamp",
          extrapolateLeft: "clamp",
          easing: EASE,
        }),
      }}
    >
      <div style={{ fontFamily: font, fontWeight: 900, fontSize: 64, color: "#fff", textShadow: "0 4px 18px rgba(0,0,0,.95)", lineHeight: 1 }}>
        {name}
      </div>
      <div style={{ height: 5, width: 230 * w, background: `linear-gradient(90deg, ${style.accent}, ${style.accent2})`, margin: "8px 0" }} />
      {role ? (
        <div
          style={{
            fontFamily: font,
            fontWeight: 700,
            fontSize: 26,
            color: style.accent,
            letterSpacing: 1.5,
            textShadow: "0 2px 14px rgba(0,0,0,.95)",
            opacity: interpolate(frame, [16, 28], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
          }}
        >
          {role}
        </div>
      ) : null}
    </div>
  );
};

/* ---------- зум по смыслу ---------- */
export const zoomAt = (frame: number, marks: [number, number][], fps: number, style: Style) => {
  const t = frame / fps;
  const m = [...marks].reverse().find((x) => t >= x[0]) ?? marks[0];
  if (!m) return 1;
  return interpolate(frame, [m[0] * fps, m[0] * fps + style.motion.zoomFrames], [1, m[1]], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
    easing: EASE,
  });
};
