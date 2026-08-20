/**
 * Стили монтажа. Один и тот же ролик собирается в любом из них — меняется
 * только пресет. Эмодзи по умолчанию выключены везде: они удешевляют картинку.
 *
 * Стиль отвечает за две независимые вещи:
 *   · как выглядит — палитра, типографика, декор;
 *   · как двигается — темп (`pacing`): скорость склеек, зумов и появления титров.
 *
 * Темп вынесен отдельно, потому что один и тот же внешний вид нужен и
 * в спокойном обзоре, и в быстром продающем ролике.
 */

export type Lang = "ru" | "hy" | "en";

export type CaptionKind = "karaoke" | "punch" | "plate" | "minimal";

/** Темп монтажа — насколько резко всё происходит. */
export type Pacing = "calm" | "normal" | "fast" | "punch";

export type PacingSpec = {
  /** за сколько кадров сцена входит в кадр */
  enterFrames: number;
  /** за сколько кадров отрабатывает зум */
  zoomFrames: number;
  /** рекомендуемая длина сцены, сек — подсказка для сборки плана */
  sceneSec: [number, number];
};

export const PACING: Record<Pacing, PacingSpec> = {
  calm: { enterFrames: 14, zoomFrames: 30, sceneSec: [4.0, 6.0] },
  normal: { enterFrames: 9, zoomFrames: 18, sceneSec: [3.0, 4.5] },
  fast: { enterFrames: 6, zoomFrames: 11, sceneSec: [2.0, 3.0] },
  punch: { enterFrames: 4, zoomFrames: 7, sceneSec: [1.2, 2.2] },
};

export type Style = {
  id: string;
  name: string;
  /** когда брать — короткая подсказка для выбора */
  use: string;
  /** палитра */
  accent: string;
  accent2: string;
  ink: string;
  textOn: string;
  textOff: string;
  /** темп движения */
  pacing: Pacing;
  /** субтитры */
  caption: {
    kind: CaptionKind;
    fontSize: number;
    /** насколько приподнять над безопасной зоной площадки */
    lift: number;
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

/** 1. Тёплая студия — под кирпич, дерево, лампы. Спокойный премиум. */
export const warmStudio: Style = {
  ...base,
  id: "warm-studio",
  name: "Тёплая студия",
  use: "экспертный тон, разговор в кадре, спокойная подача",
  accent: "#f59e0b",
  accent2: "#8b5cf6",
  pacing: "normal",
  caption: { kind: "karaoke", fontSize: 43, lift: 0, align: "left",
             plate: "rgba(12,9,6,.66)", radius: 14, stroke: 0, uppercase: false, maxWidth: 600 },
  punch: { fontSize: 74, stroke: 9, top: 210, underline: true, twoTone: true },
  decor: { brackets: true, bokeh: 30, progressBar: true, badge: true, vignette: 0.18 },
  motion: { zoomAmount: 1.08, zoomFrames: 18, captionPopScale: 0.96 },
};

/** 2. Дерзкий оранжевый — высокая динамика, крупные капсы, продающие ролики. */
export const boldOrange: Style = {
  ...base,
  id: "bold-orange",
  name: "Дерзкий оранжевый",
  use: "продажа в лоб, хайп, распаковка, находка",
  accent: "#f37810",
  accent2: "#ffffff",
  pacing: "fast",
  caption: { kind: "punch", fontSize: 56, lift: 0, align: "center",
             plate: null, radius: 0, stroke: 9, uppercase: true, maxWidth: 660 },
  punch: { fontSize: 84, stroke: 10, top: 230, underline: true, twoTone: true },
  decor: { brackets: true, bokeh: 46, progressBar: true, badge: true, vignette: 0.3 },
  motion: { zoomAmount: 1.14, zoomFrames: 10, captionPopScale: 0.62 },
};

/** 3. Чистый минимал — ничего лишнего, деловой тон. */
export const cleanMinimal: Style = {
  ...base,
  id: "clean-minimal",
  name: "Чистый минимал",
  use: "инструкция, гайд, объяснение без давления",
  accent: "#ffffff",
  accent2: "#9ca3af",
  pacing: "normal",
  caption: { kind: "plate", fontSize: 42, lift: 0, align: "center",
             plate: "rgba(0,0,0,.55)", radius: 10, stroke: 0, uppercase: false, maxWidth: 620 },
  punch: { fontSize: 64, stroke: 0, top: 220, underline: false, twoTone: false },
  decor: { brackets: false, bokeh: 0, progressBar: false, badge: false, vignette: 0.1 },
  motion: { zoomAmount: 1.04, zoomFrames: 26, captionPopScale: 0.98 },
};

/** 4. Ночной неон — тёмный кадр, свечение, техно и AI. */
export const neonNight: Style = {
  ...base,
  id: "neon-night",
  name: "Ночной неон",
  use: "техника, гаджеты, тёмный кадр",
  accent: "#22d3ee",
  accent2: "#a855f7",
  ink: "#07070d",
  pacing: "fast",
  caption: { kind: "karaoke", fontSize: 44, lift: 0, align: "left",
             plate: "rgba(7,7,13,.7)", radius: 12, stroke: 0, uppercase: false, maxWidth: 610 },
  punch: { fontSize: 76, stroke: 8, top: 205, underline: false, twoTone: true },
  decor: { brackets: true, bokeh: 38, progressBar: true, badge: true, vignette: 0.34 },
  motion: { zoomAmount: 1.1, zoomFrames: 14, captionPopScale: 0.9 },
};

/** 5. Свежая мята — чистота, стирка, уборка, вода. Светлый кадр. */
export const freshMint: Style = {
  ...base,
  id: "fresh-mint",
  name: "Свежая мята",
  use: "бытовая химия, чистота, до/после, вода",
  accent: "#12b981",
  accent2: "#38bdf8",
  ink: "#04231c",
  pacing: "normal",
  caption: { kind: "karaoke", fontSize: 46, lift: 10, align: "center",
             plate: "rgba(4,35,28,.62)", radius: 16, stroke: 0, uppercase: false, maxWidth: 630 },
  punch: { fontSize: 78, stroke: 8, top: 215, underline: true, twoTone: true },
  decor: { brackets: false, bokeh: 22, progressBar: true, badge: true, vignette: 0.14 },
  motion: { zoomAmount: 1.07, zoomFrames: 20, captionPopScale: 0.94 },
};

/**
 * 6. Мягкий крем — светлый кадр и тёмный текст. Единственный стиль
 * со светлой типографикой: на белой ванной и постели белый текст пропадает.
 */
export const softCream: Style = {
  ...base,
  id: "soft-cream",
  name: "Мягкий крем",
  use: "косметика, уход, дом, светлый кадр",
  accent: "#c2410c",
  accent2: "#a16207",
  ink: "#fdf6ec",
  textOn: "#2b1d12",
  textOff: "rgba(43,29,18,.35)",
  pacing: "calm",
  caption: { kind: "plate", fontSize: 42, lift: 6, align: "center",
             plate: "rgba(253,246,236,.88)", radius: 14, stroke: 0, uppercase: false, maxWidth: 620 },
  punch: { fontSize: 70, stroke: 0, top: 220, underline: true, twoTone: true },
  decor: { brackets: false, bokeh: 0, progressBar: false, badge: true, vignette: 0.06 },
  motion: { zoomAmount: 1.05, zoomFrames: 28, captionPopScale: 0.97 },
};

/** 7. Моно-контраст — чёрно-белое с одним акцентом. Дорого и строго. */
export const monoPunch: Style = {
  ...base,
  id: "mono-punch",
  name: "Моно-контраст",
  use: "премиум, сравнение, строгий разбор без украшений",
  accent: "#ef4444",
  accent2: "#ffffff",
  ink: "#000000",
  pacing: "punch",
  caption: { kind: "punch", fontSize: 52, lift: 0, align: "center",
             plate: null, radius: 0, stroke: 8, uppercase: true, maxWidth: 640 },
  punch: { fontSize: 92, stroke: 12, top: 240, underline: false, twoTone: true },
  decor: { brackets: false, bokeh: 0, progressBar: false, badge: false, vignette: 0.4 },
  motion: { zoomAmount: 1.16, zoomFrames: 8, captionPopScale: 0.58 },
};

/** 8. Ночное золото — тёмный кадр с тёплым металлом. Дорогой товар. */
export const nightGold: Style = {
  ...base,
  id: "night-gold",
  name: "Ночное золото",
  use: "премиальный товар, украшения, подарок",
  accent: "#d4af37",
  accent2: "#f5e6b8",
  ink: "#0b0a07",
  pacing: "calm",
  caption: { kind: "karaoke", fontSize: 44, lift: 8, align: "center",
             plate: "rgba(11,10,7,.7)", radius: 12, stroke: 0, uppercase: false, maxWidth: 610 },
  punch: { fontSize: 74, stroke: 6, top: 210, underline: false, twoTone: true },
  decor: { brackets: true, bokeh: 18, progressBar: false, badge: true, vignette: 0.36 },
  motion: { zoomAmount: 1.06, zoomFrames: 26, captionPopScale: 0.95 },
};

export const STYLES: Record<string, Style> = {
  [warmStudio.id]: warmStudio,
  [boldOrange.id]: boldOrange,
  [cleanMinimal.id]: cleanMinimal,
  [neonNight.id]: neonNight,
  [freshMint.id]: freshMint,
  [softCream.id]: softCream,
  [monoPunch.id]: monoPunch,
  [nightGold.id]: nightGold,
};

export const getStyle = (id?: string): Style => STYLES[id ?? ""] ?? warmStudio;

/** Темп стиля, если спека не переопределила его своим. */
export const getPacing = (style: Style, override?: Pacing): PacingSpec =>
  PACING[override ?? style.pacing] ?? PACING.normal;

/** Шрифты по языку — Anton не знает кириллицы, системные не знают армянского. */
export const FONT_FOR: Record<Lang, { file: string; family: string; weight?: number }> = {
  ru: { file: "Montserrat-Black.ttf", family: "MontBlack", weight: 900 },
  hy: { file: "NotoArm.ttf", family: "NotoArm", weight: 900 },
  en: { file: "Anton-Regular.ttf", family: "Anton" },
};
