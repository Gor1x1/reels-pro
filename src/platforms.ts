/**
 * Безопасные зоны площадок. Интерфейс каждой сети перекрывает часть кадра:
 * снизу подпись и автор, справа колонка кнопок, сверху поиск и вкладки.
 * Всё, что попало под них, зритель не увидит.
 *
 * Доли от размера кадра, а не пиксели — макет не зависит от разрешения.
 * Мастер один на семь сетей, поэтому по умолчанию берётся `multi` —
 * пересечение свободных областей всех сетей.
 */

export type Platform =
  | "tiktok"
  | "instagram"
  | "shorts"
  | "vk"
  | "ok"
  | "likee"
  | "facebook"
  | "multi";

export type SafeZone = {
  /** доля кадра сверху, занятая интерфейсом */
  top: number;
  bottom: number;
  left: number;
  right: number;
};

/**
 * Замеры сделаны по вертикальному кадру 1080×1920 на телефоне среднего размера.
 * Значения намеренно с запасом: подпись у длинного текста разворачивается
 * на две-три строки и съедает больше, чем в свёрнутом виде.
 */
export const SAFE: Record<Platform, SafeZone> = {
  tiktok: { top: 0.09, bottom: 0.22, left: 0.04, right: 0.15 },
  instagram: { top: 0.08, bottom: 0.24, left: 0.04, right: 0.14 },
  shorts: { top: 0.07, bottom: 0.2, left: 0.04, right: 0.14 },
  vk: { top: 0.08, bottom: 0.21, left: 0.04, right: 0.13 },
  ok: { top: 0.08, bottom: 0.2, left: 0.04, right: 0.12 },
  likee: { top: 0.09, bottom: 0.22, left: 0.04, right: 0.14 },
  facebook: { top: 0.08, bottom: 0.23, left: 0.04, right: 0.14 },
  /** пересечение всех семи — сюда влезает то, что видно везде */
  multi: { top: 0.09, bottom: 0.24, left: 0.04, right: 0.15 },
};

/** Свободный прямоугольник в пикселях под конкретный кадр. */
export const safeBox = (p: Platform, w: number, h: number) => {
  const z = SAFE[p] ?? SAFE.multi;
  return {
    top: Math.round(h * z.top),
    bottom: Math.round(h * z.bottom),
    left: Math.round(w * z.left),
    right: Math.round(w * z.right),
    width: Math.round(w * (1 - z.left - z.right)),
    height: Math.round(h * (1 - z.top - z.bottom)),
  };
};

/**
 * Нижняя граница для субтитров: отступ от низа кадра, ниже которого
 * текст уходит под подпись. Стиль задаёт `captionLift` — насколько
 * приподнять относительно этой границы.
 */
export const captionBottom = (p: Platform, h: number, lift = 0) =>
  Math.round(h * (SAFE[p] ?? SAFE.multi).bottom) + lift;

/** Сверху: под этой линией можно ставить титры. */
export const topLine = (p: Platform, h: number) =>
  Math.round(h * (SAFE[p] ?? SAFE.multi).top);
