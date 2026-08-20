/**
 * Анимации субтитров. Каждая — чистая функция: по времени и слову отдаёт стиль.
 * Компонент субтитров один, вид переключается строкой в спеке или стиле.
 *
 * Правила, по которым это выглядит дорого, а не как шаблон из редактора:
 *   · один эффект за раз — движение ИЛИ размытие ИЛИ подсветка, не всё сразу;
 *   · вход быстрый (0.1–0.2 с), выход не анимируется вовсе — глаз цепляется
 *     за появление, а исчезновение читается как тормоз;
 *   · overshoot маленький: 1.06 читается как упругость, 1.4 — как дешёвый шаблон;
 *   · никаких вращений, тресёра и радужных обводок.
 */
import { interpolate, Easing } from "remotion";
import type { CSSProperties } from "react";

/** Мягкое торможение — то же, что во всём остальном ките. */
export const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
/** Упругость с лёгким перелётом — для акцентных слов. */
export const EASE_BACK = Easing.bezier(0.34, 1.56, 0.64, 1);

export type CaptionAnim =
  | "karaoke"
  | "word-pop"
  | "blur-in"
  | "mask-wipe"
  | "typewriter"
  | "highlight"
  | "stagger-up"
  | "glow"
  | "zoom-punch";

export const CAPTION_ANIMS: CaptionAnim[] = [
  "karaoke",
  "word-pop",
  "blur-in",
  "mask-wipe",
  "typewriter",
  "highlight",
  "stagger-up",
  "glow",
  "zoom-punch",
];

export type AnimCtx = {
  /** текущее время ролика, сек */
  t: number;
  /** начало и конец слова, сек */
  s: number;
  e: number;
  /** индекс слова внутри блока */
  i: number;
  /** начало блока, сек */
  blockStart: number;
  accent: string;
  accent2: string;
  textOn: string;
  textOff: string;
  ink: string;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** Сколько прошло с момента, когда слово прозвучало (может быть отрицательным). */
const since = (c: AnimCtx) => c.t - c.s;

/**
 * Стиль отдельного слова. Возвращает только то, что отличает это слово от
 * соседей — цвет, масштаб, размытие. Общая типографика живёт в компоненте.
 */
export const wordStyle = (anim: CaptionAnim, c: AnimCtx): CSSProperties => {
  const d = since(c);
  const spoken = d >= -0.02;

  switch (anim) {
    /** Сказанное белым, будущее приглушено. Спокойно, читается на любом фоне. */
    case "karaoke":
      return { color: spoken ? c.textOn : c.textOff };

    /** Слово выскакивает в момент произнесения. Живо, но без клоунады. */
    case "word-pop":
      return {
        color: spoken ? c.textOn : c.textOff,
        scale: spoken
          ? interpolate(d, [0, 0.16], [0.86, 1], { ...clamp, easing: EASE_BACK })
          : 0.94,
      };

    /** Из размытия в резкость. Самый «дорогой» на вид, хорошо под премиум. */
    case "blur-in":
      return {
        color: c.textOn,
        opacity: interpolate(d, [-0.06, 0.14], [0, 1], clamp),
        filter: `blur(${interpolate(d, [-0.06, 0.18], [9, 0], clamp)}px)`,
      };

    /** Слова открываются по очереди — сама маска живёт в blockStyle. */
    case "mask-wipe":
      return { color: c.textOn };

    /** Посимвольная печать — текст режется в компоненте. */
    case "typewriter":
      return { color: c.textOn };

    /** Активное слово в плашке акцентного цвета. Тиктоковый приём, но чистый. */
    case "highlight":
      return spoken && c.t <= c.e + 0.08
        ? {
            color: c.ink,
            background: c.accent,
            borderRadius: 8,
            padding: "2px 10px",
            margin: "0 -2px",
          }
        : { color: spoken ? c.textOn : c.textOff };

    /** Каждое слово поднимается снизу с задержкой по порядку. */
    case "stagger-up": {
      const local = c.t - c.blockStart - c.i * 0.055;
      return {
        color: c.textOn,
        opacity: interpolate(local, [0, 0.12], [0, 1], clamp),
        translate: `0px ${interpolate(local, [0, 0.26], [26, 0], {
          ...clamp,
          easing: EASE_OUT,
        })}px`,
      };
    }

    /** Свечение на активном слове — под тёмный кадр и неон. */
    case "glow":
      return spoken && c.t <= c.e + 0.12
        ? {
            color: c.textOn,
            textShadow: `0 0 ${interpolate(d, [0, 0.2], [26, 12], clamp)}px ${c.accent}, 0 0 6px ${c.accent}`,
          }
        : { color: spoken ? c.textOn : c.textOff };

    /** Сильный удар: слово приходит крупным и садится на место. */
    case "zoom-punch":
      return {
        color: spoken ? c.accent : c.textOff,
        scale: spoken
          ? interpolate(d, [0, 0.13], [1.34, 1], { ...clamp, easing: EASE_OUT })
          : 1,
      };

    default:
      return { color: spoken ? c.textOn : c.textOff };
  }
};

/**
 * Стиль всего блока. Здесь живёт появление блока целиком и маска для wipe.
 * `local` — время от начала блока в секундах.
 */
export const blockStyle = (anim: CaptionAnim, local: number): CSSProperties => {
  switch (anim) {
    case "mask-wipe": {
      const p = interpolate(local, [0, 0.42], [0, 100], { ...clamp, easing: EASE_OUT });
      const mask = `linear-gradient(90deg, #000 ${p}%, transparent ${Math.min(p + 8, 100)}%)`;
      return { WebkitMaskImage: mask, maskImage: mask };
    }

    /** Блок целиком не двигаем — слова приходят по одному. */
    case "stagger-up":
    case "typewriter":
      return {};

    default:
      return {
        opacity: interpolate(local, [0, 0.1], [0, 1], clamp),
        scale: interpolate(local, [0, 0.2], [0.97, 1], { ...clamp, easing: EASE_OUT }),
      };
  }
};

/**
 * Для печатной машинки: сколько символов блока уже напечатано.
 * Скорость привязана к речи — печатаем ровно до того слова, что звучит.
 */
export const typedLength = (words: { t: string; s: number; e: number }[], t: number) => {
  let n = 0;
  for (const w of words) {
    if (t >= w.e) {
      n += w.t.length + 1;
      continue;
    }
    if (t >= w.s) {
      const p = (t - w.s) / Math.max(w.e - w.s, 0.06);
      n += Math.round(w.t.length * Math.min(Math.max(p, 0), 1));
    }
    break;
  }
  return n;
};

/** Анимация, которая не спорит с характером стиля — используется как дефолт. */
export const DEFAULT_ANIM_FOR: Record<string, CaptionAnim> = {
  "warm-studio": "blur-in",
  "bold-orange": "word-pop",
  "clean-minimal": "karaoke",
  "neon-night": "glow",
};
