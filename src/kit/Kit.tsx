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
import {
  wordStyle,
  blockStyle,
  typedLength,
  DEFAULT_ANIM_FOR,
  type CaptionAnim,
} from "../captions/anim";
import { captionBottom, topLine, type Platform } from "../platforms";

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

/**
 * Сколько места занимает строка субтитров вместе с плашкой и отступами.
 * По этой величине всё, что ставится над субтитрами, отодвигается вверх —
 * иначе элементы наезжают друг на друга и текст пропадает.
 *
 * Считается по размеру шрифта: две строки плюс поля плашки плюс зазор,
 * который должен остаться видимым.
 */
export const captionBlockHeight = (style: Style): number =>
  Math.round(style.caption.fontSize * 1.24 * 2 + (style.caption.plate ? 20 : 0) + 34);

/**
 * Ширина строки настоящим шрифтом кадра.
 *
 * Оценка «число символов × коэффициент» на армянском промахивается: буквы
 * заметно шире латиницы, и строка уезжает за край кадра — у артикула так
 * обрезались крайние цифры, а по ним покупатель ищет товар.
 */
export const textWidth = (text: string, font: string, weight: number, size: number): number => {
  const guess = text.length * size * 0.62;
  try {
    const ctx = document.createElement("canvas").getContext("2d");
    if (!ctx) return guess;
    ctx.font = `${weight} ${size}px ${font}`;
    const w = ctx.measureText(text).width;
    return w > 0 ? w : guess;
  } catch {
    return guess;
  }
};

/**
 * Размер шрифта, при котором строка целиком помещается в отведённую ширину.
 * Уменьшаем только если не влезает: крупный артикул читается с телефона,
 * мелкий — нет.
 */
export const fitFontSize = (
  text: string, font: string, weight: number, maxSize: number,
  maxWidth: number, minSize = 30,
): number => {
  const w = textWidth(text, font, weight, maxSize);
  if (w <= maxWidth) return maxSize;
  return Math.max(minSize, Math.floor((maxSize * maxWidth) / w));
};

/**
 * Вид анимации приходит из спеки или из стиля — компонент один на все девять.
 * Нижняя граница считается от безопасной зоны площадки, а не задаётся числом:
 * под подписью и кнопками субтитры зритель просто не увидит.
 */
export const Captions: React.FC<{
  blocks: KBlock[];
  style: Style;
  lang: Lang;
  fps?: number;
  anim?: CaptionAnim;
  platform?: Platform;
  /** высота кадра в координатах макета */
  frameHeight?: number;
  /** приподнять над безопасной границей */
  lift?: number;
  /** отрезки в секундах, на которых субтитры не показываются */
  hideDuring?: [number, number][];
}> = ({
  blocks,
  style,
  lang,
  fps = 30,
  anim,
  platform = "multi",
  frameHeight = 1280,
  lift = 0,
  hideDuring,
}) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const t = frame / fps;
  const c = style.caption;
  const a: CaptionAnim = anim ?? DEFAULT_ANIM_FOR[style.id] ?? "karaoke";

  if (hideDuring?.some(([from, to]) => t >= from && t < to)) return null;

  /**
   * Блок висит до начала следующего, а не пропадает на последнем слове.
   * Человек дочитывает фразу уже после того, как её произнесли, и если
   * текст исчезает в момент последнего звука, мысль читается оборванной.
   * Дольше 0.9 с после конца не держим — иначе субтитр отстаёт от картинки.
   */
  const HOLD = 0.9;
  let b: KBlock | undefined;
  for (let i = 0; i < blocks.length; i++) {
    const cur = blocks[i];
    if (t < cur.start - 0.08) break;
    const next = blocks[i + 1];
    const until = next
      ? Math.max(Math.min(next.start - 0.05, cur.end + HOLD), cur.end + 0.12)
      : cur.end + HOLD;
    if (t <= until) {
      b = cur;
      break;
    }
  }
  if (!b) return null;
  const local = t - b.start;

  const ctxBase = {
    t,
    blockStart: b.start,
    accent: style.accent,
    accent2: style.accent2,
    textOn: style.textOn,
    textOff: style.textOff,
    ink: style.ink,
  };

  /** печатная машинка режет текст, остальные анимации работают по словам */
  const cut = a === "typewriter" ? typedLength(b.words, t) : Infinity;
  let used = 0;

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
        const start = used;
        used += w.t.length + 1;
        if (a === "typewriter" && start >= cut) return null;
        const text = a === "typewriter" ? w.t.slice(0, Math.max(cut - start, 0)) : w.t;

        return (
          <span
            key={i}
            style={{
              marginRight: 10,
              display: "inline-block",
              WebkitTextStroke: c.stroke ? `${c.stroke}px ${style.ink}` : undefined,
              paintOrder: "stroke fill",
              textShadow: c.plate ? undefined : `0 3px 0 ${style.ink}, 0 0 20px rgba(0,0,0,.85)`,
              ...wordStyle(a, { ...ctxBase, s: w.s, e: w.e, i }),
            }}
          >
            {text}
          </span>
        );
      })}
    </span>
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: captionBottom(platform, frameHeight, lift),
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
          ...blockStyle(a, local),
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
  /** длительность показа в кадрах — по ней титр плавно уходит */
  dur?: number;
}> = ({ line1, line2, style, lang, dur }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const p = style.punch;
  const out =
    dur && dur > 12
      ? interpolate(frame, [dur - 6, dur], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
      : 1;

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
    <div
      style={{
        position: "absolute",
        top: p.top,
        left: 0,
        width: "100%",
        padding: "0 26px",
        boxSizing: "border-box",
        opacity: out,
      }}
    >
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
/**
 * Бейдж бренда. Справа внизу его ставить нельзя: там колонка кнопок площадки
 * и подпись — на телефоне он окажется под интерфейсом. Место по умолчанию —
 * левый верх, под строкой поиска.
 */
export const Badge: React.FC<{
  style: Style;
  text?: string;
  src?: string;
  lang?: Lang;
  size?: number;
  platform?: Platform;
  frameHeight?: number;
}> = ({ style, text, src, lang = "en", size = 86, platform = "multi", frameHeight = 1280 }) => {
  const font = useFont(lang);
  const frame = useCurrentFrame();
  // Бейдж появляется, только если бренд задан в спеке. Никаких значений
  // по умолчанию: чужой логотип в кадре — брак, который заметят все.
  if (!style.decor.badge || (!text && !src)) return null;
  const spin = interpolate(frame, [0, 260], [0, 360]);
  return (
    <div
      style={{
        position: "absolute",
        left: 34,
        top: topLine(platform, frameHeight) + 18,
        width: size,
        height: size,
        opacity: interpolate(frame, [0, 14], [0, 1], { extrapolateRight: "clamp" }),
      }}
    >
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
/** `zoomFrames` приходит из темпа монтажа, а не из стиля: один и тот же
 *  внешний вид нужен и в спокойном обзоре, и в быстром продающем ролике. */
export const zoomAt = (frame: number, marks: [number, number][], fps: number, zoomFrames: number) => {
  const t = frame / fps;
  const m = [...marks].reverse().find((x) => t >= x[0]) ?? marks[0];
  if (!m) return 1;
  return interpolate(frame, [m[0] * fps, m[0] * fps + zoomFrames], [1, m[1]], {
    extrapolateRight: "clamp",
    extrapolateLeft: "clamp",
    easing: EASE,
  });
};
