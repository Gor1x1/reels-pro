/**
 * Стили монтажа. Один и тот же ролик собирается в любом из них — меняется
 * только пресет. Эмодзи по умолчанию выключены везде: они удешевляют картинку.
 */

export type Lang = "ru" | "hy" | "en";

export type CaptionKind = "karaoke" | "punch" | "plate" | "minimal";

export type Style = {
  id: string;
  name: string;
  /** палитра */
  accent: string;
  accent2: string;
  ink: string;
  textOn: string;
  textOff: string;
  /** субтитры */
  caption: {
    kind: CaptionKind;
    fontSize: number;
    bottom: number;
    align: "left" | "center";
    plate: string | null;
    radius: number;
    stroke: number;
    uppercase: boolean;
    maxWidth: number;
  };
  /** акцентные титры поверх видео */
  punch: {
    fontSize: number;
    stroke: number;
    top: number;
    underline: boolean;
    twoTone: boolean; // вторая строка акцентным цветом
  };
  /** декор */
  decor: {
    brackets: boolean;
    bokeh: number; // 0 = выключено
    progressBar: boolean;
    badge: boolean;
    vignette: number; // 0..1
  };
  /** движение */
  motion: {
    zoomAmount: number; // насколько сильный punch-in
    zoomFrames: number; // за сколько кадров
    captionPopScale: number;
  };
  emoji: boolean;
};

const base = {
  ink: "#0d0a08",
  textOn: "#ffffff",
  textOff: "rgba(255,255,255,.38)",
  emoji: false,
};

/** 1. Тёплая студия — под кирпич/дерево/лампы. Спокойный премиум. */
export const warmStudio: Style = {
  ...base,
  id: "warm-studio",
  name: "Тёплая студия",
  accent: "#f59e0b",
  accent2: "#8b5cf6",
  caption: {
    kind: "karaoke",
    fontSize: 43,
    bottom: 252,
    align: "left",
    plate: "rgba(12,9,6,.66)",
    radius: 14,
    stroke: 0,
    uppercase: false,
    maxWidth: 600,
  },
  punch: { fontSize: 74, stroke: 9, top: 210, underline: true, twoTone: true },
  decor: { brackets: true, bokeh: 30, progressBar: true, badge: true, vignette: 0.18 },
  motion: { zoomAmount: 1.08, zoomFrames: 18, captionPopScale: 0.96 },
};

/** 2. Дерзкий оранжевый — высокая динамика, крупные капсы, для хайповых тем. */
export const boldOrange: Style = {
  ...base,
  id: "bold-orange",
  name: "Дерзкий оранжевый",
  accent: "#f37810",
  accent2: "#ffffff",
  caption: {
    kind: "punch",
    fontSize: 56,
    bottom: 300,
    align: "center",
    plate: null,
    radius: 0,
    stroke: 9,
    uppercase: true,
    maxWidth: 660,
  },
  punch: { fontSize: 84, stroke: 10, top: 230, underline: true, twoTone: true },
  decor: { brackets: true, bokeh: 46, progressBar: true, badge: true, vignette: 0.3 },
  motion: { zoomAmount: 1.14, zoomFrames: 10, captionPopScale: 0.62 },
};

/** 3. Чистый минимал — ничего лишнего, для экспертного/делового тона. */
export const cleanMinimal: Style = {
  ...base,
  id: "clean-minimal",
  name: "Чистый минимал",
  accent: "#ffffff",
  accent2: "#9ca3af",
  caption: {
    kind: "plate",
    fontSize: 42,
    bottom: 260,
    align: "center",
    plate: "rgba(0,0,0,.55)",
    radius: 10,
    stroke: 0,
    uppercase: false,
    maxWidth: 620,
  },
  punch: { fontSize: 64, stroke: 0, top: 220, underline: false, twoTone: false },
  decor: { brackets: false, bokeh: 0, progressBar: false, badge: false, vignette: 0.1 },
  motion: { zoomAmount: 1.04, zoomFrames: 26, captionPopScale: 0.98 },
};

/** 4. Ночной неон — тёмный кадр, свечение, для техно/AI-тем. */
export const neonNight: Style = {
  ...base,
  id: "neon-night",
  name: "Ночной неон",
  accent: "#22d3ee",
  accent2: "#a855f7",
  ink: "#07070d",
  caption: {
    kind: "karaoke",
    fontSize: 44,
    bottom: 268,
    align: "left",
    plate: "rgba(7,7,13,.7)",
    radius: 12,
    stroke: 0,
    uppercase: false,
    maxWidth: 610,
  },
  punch: { fontSize: 76, stroke: 8, top: 205, underline: false, twoTone: true },
  decor: { brackets: true, bokeh: 38, progressBar: true, badge: true, vignette: 0.34 },
  motion: { zoomAmount: 1.1, zoomFrames: 14, captionPopScale: 0.9 },
};

export const STYLES: Record<string, Style> = {
  [warmStudio.id]: warmStudio,
  [boldOrange.id]: boldOrange,
  [cleanMinimal.id]: cleanMinimal,
  [neonNight.id]: neonNight,
};

export const getStyle = (id?: string): Style => STYLES[id ?? ""] ?? warmStudio;

/** Шрифты по языку — Anton не знает кириллицы, системные не знают армянского. */
export const FONT_FOR: Record<Lang, { file: string; family: string; weight?: number }> = {
  ru: { file: "Montserrat-Black.ttf", family: "MontBlack", weight: 900 },
  hy: { file: "NotoArm.ttf", family: "NotoArm", weight: 900 },
  en: { file: "Anton-Regular.ttf", family: "Anton" },
};
