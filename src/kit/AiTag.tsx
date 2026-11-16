/**
 * Метка «AI» — честная подпись персонажа, сделанного нейросетью.
 *
 * Сначала полная плашка (например «[AI] character · not a real person») —
 * на хуке, где речь говорит то же самое. Потом плашка сворачивается
 * в маленькую таблетку «AI», и таблетка стоит до конца ролика: в ролике
 * без речи она остаётся единственным текстом, поэтому живёт поверх всего
 * монтажа, а не внутри сцены.
 *
 * Поле спеки `aiTag` необязательное: без него ничего не рисуется, и старые
 * спеки собираются как раньше. Введено для серии V (Vera Lin, 09.10.2026).
 * Цвет выбирается по замеру яркости фона под меткой, а не на глаз. V01:
 * под таблеткой окно и штора (L 0.56–0.90) — белая 1.1–1.7:1, синяя
 * 2.7–4.2:1, тёмная 10.8–16.9:1; под полной плашкой середина — волосы
 * (L 0.11–0.20), края — штора (L 0.39–0.60): худший участок у белой 1.6:1,
 * у тёмной 2.9:1, и его закрывает светлый кант. См.
 * runs/2026-10-09/V01/grafika-yarkost.json.
 */
import { useCurrentFrame, interpolate, Easing } from "remotion";
import type { Lang, Style } from "../styles";
import { EASE, textWidth, useFont } from "./Kit";

export type AiTagSpec = {
  /** текст таблетки, по умолчанию «AI» */
  text?: string;
  /** продолжение полной плашки после таблетки; без него сразу таблетка */
  full?: string;
  /** сколько секунд от `at` держится полная плашка, потом сворачивается */
  fullDur?: number;
  /** появление, секунды ролика; 0 — с первого кадра, без проявления */
  at?: number;
  /** сколько держится всего, секунды; без него — до конца ролика */
  dur?: number;
  /** центр таблетки в долях кадра */
  x?: number;
  y?: number;
  /** центр полной плашки в долях кадра; по умолчанию x 0.5 и y таблетки */
  fullX?: number;
  fullY?: number;
  /** кегль таблетки и полной плашки, пиксели макета 720×1280 */
  size?: number;
  fullSize?: number;
  /** заливка и текст таблетки */
  bg?: string;
  color?: string;
  /** заливка и текст полной плашки; по умолчанию как у таблетки */
  fullBg?: string;
  fullColor?: string;
};

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const W = 720;
const H = 1280;
/** кадров на сворачивание плашки в таблетку: плавно с обоих концов, чтобы глаз видел, куда она уехала */
const COLLAPSE = 14;

/** Размер таблетки при кегле `s`: поля от кегля, ширина — настоящим шрифтом. */
const chipBox = (text: string, font: string, s: number) => {
  const padX = s * 0.42;
  const padY = s * 0.2;
  const w = textWidth(text, font, 900, s) + text.length * 1 + 2 * padX;
  const h = s * 1.1 + 2 * padY;
  return { w, h, padX, padY };
};

export const AiTag: React.FC<{
  tag: AiTagSpec;
  style: Style;
  lang: Lang;
  fontKey?: string;
  fps: number;
  total: number;
}> = ({ tag, style, lang, fontKey, fps, total }) => {
  const font = useFont(lang, fontKey);
  const frame = useCurrentFrame();
  const at = Math.round((tag.at ?? 0) * fps);
  const end = tag.dur !== undefined ? at + Math.round(tag.dur * fps) : total;
  const f = frame - at;
  if (f < 0 || frame >= end) return null;

  const text = tag.text ?? "AI";
  const size = tag.size ?? 22;
  const fullSize = tag.fullSize ?? size;
  const bg = tag.bg ?? "#10131a";
  const color = tag.color ?? "#ffffff";
  const px = (tag.x ?? 0.17) * W;
  const py = (tag.y ?? 0.16) * H;

  // вход: с первого кадра ролика — сразу, иначе мягко; выход — только если задан `dur`
  const inO = at === 0 ? 1 : interpolate(f, [0, 8], [0, 1], { ...clamp, easing: EASE });
  const outO = tag.dur !== undefined ? interpolate(frame, [end - 6, end], [1, 0], clamp) : 1;
  const o = Math.min(inO, outO);

  // полная плашка и её сворачивание
  const fullF = tag.full ? Math.round((tag.fullDur ?? 2.5) * fps) : 0;
  const k = tag.full ? interpolate(f, [fullF, fullF + COLLAPSE], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) }) : 1;

  const chipFull = chipBox(text, font, fullSize);
  const restW = tag.full ? textWidth(tag.full, font, 900, fullSize) + tag.full.length * 0.3 : 0;
  const padL = fullSize * 0.32;
  const padR = fullSize * 0.62;
  const gap = fullSize * 0.45;
  const plateW = padL + chipFull.w + gap + restW + padR;
  const plateH = chipFull.h + fullSize * 0.56;
  const fcx = (tag.fullX ?? 0.5) * W;
  const fcy = (tag.fullY ?? tag.y ?? 0.16) * H;
  const plateLeft = fcx - plateW / 2;
  const chipFullX = plateLeft + padL + chipFull.w / 2;

  // таблетка: из своего места в плашке — в постоянное место
  const s = interpolate(k, [0, 1], [fullSize, size]);
  const chip = chipBox(text, font, s);
  const cx = interpolate(k, [0, 1], [chipFullX, px]);
  const cy = interpolate(k, [0, 1], [fcy, py]);
  const pop = at === 0 ? 1 : interpolate(f, [0, 9], [0.86, 1], { ...clamp, easing: EASE });

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", opacity: o }}>
      {tag.full && k < 1 ? (
        <div
          style={{
            position: "absolute",
            left: plateLeft,
            top: fcy - plateH / 2,
            width: plateW,
            height: plateH,
            boxSizing: "border-box",
            borderRadius: plateH / 2,
            background: tag.fullBg ?? bg,
            border: "1.5px solid rgba(255,255,255,.85)",
            boxShadow: "0 6px 20px rgba(16,19,26,.22)",
            display: "flex",
            alignItems: "center",
            paddingLeft: padL + chipFull.w + gap,
            opacity: interpolate(k, [0, 0.55], [1, 0], clamp),
            transformOrigin: `${padL + chipFull.w / 2}px 50%`,
            scale: `${interpolate(k, [0, 1], [1, 0.9])} ${pop}`,
          }}
        >
          <span
            style={{
              fontFamily: font,
              fontWeight: 900,
              fontSize: fullSize,
              lineHeight: 1,
              letterSpacing: 0.3,
              color: tag.fullColor ?? color,
              opacity: 0.9,
              whiteSpace: "nowrap",
            }}
          >
            {tag.full}
          </span>
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: cx - chip.w / 2,
          top: cy - chip.h / 2,
          width: chip.w,
          height: chip.h,
          boxSizing: "border-box",
          borderRadius: chip.h / 2,
          background: bg,
          // тонкий светлый кант: таблетку не съедает тёмная рама окна под ней
          border: "1.5px solid rgba(255,255,255,.85)",
          boxShadow: "0 3px 10px rgba(16,19,26,.25)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily: font,
          fontWeight: 900,
          fontSize: s,
          lineHeight: 1,
          letterSpacing: 1,
          color,
          scale: `${pop}`,
        }}
      >
        {text}
      </div>
    </div>
  );
};
