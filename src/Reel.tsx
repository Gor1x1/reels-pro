/**
 * Ролик собирается из спецификации (spec.json), а не пишется руками.
 * Меняешь "style" — меняется весь внешний вид, монтаж остаётся тем же.
 *
 * Главное отличие от первой версии: сцена `clip` берёт кусок из любого файла
 * по таймкодам, поэтому один ролик собирается из четырёх-пяти источников.
 * Макет живёт в координатах 720×1280 и масштабируется в кадр вывода —
 * все размеры в стилях и компонентах остались прежними.
 */
import { AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame, useVideoConfig, interpolate } from "remotion";
import { Video, Audio } from "@remotion/media";
import { getStyle, getPacing, type Lang, type Pacing } from "./styles";
import { topLine, captionBottom, type Platform } from "./platforms";
import { type CaptionAnim } from "./captions/anim";
import {
  Badge,
  Bokeh,
  Brackets,
  Captions,
  captionBlockHeight,
  fitFontSize,
  EASE,
  NameTitle,
  Progress,
  Punch,
  Vignette,
  useFont,
  zoomAt,
  type KBlock,
} from "./kit/Kit";
import { BeforeAfter, CountUp, OfferPlate, Pointer, QuoteCard, StepBadge, type Side } from "./kit/Product";

/** Координаты макета. Кадр вывода задаётся в Root и может быть больше. */
export const DESIGN = { w: 720, h: 1280 };

/**
 * Подпись к артикулу на языке ролика. Формат совпадает с тем, что вжигает
 * раскатка на 7 личностей: покупатель должен видеть одну и ту же строку
 * и в мастере, и в любой из копий.
 */
const SKU_LABEL: Record<Lang, string> = {
  hy: "WB Արտիկուլ։",
  ru: "WB Артикул:",
  en: "WB SKU:",
};

/** Видео или картинка. Поле `isVideo` в спеке главнее, расширение — запасной вариант. */
const VIDEO_EXT = [".mp4", ".mov", ".webm", ".mkv", ".m4v"];
const looksLikeVideo = (src?: string) =>
  Boolean(src && VIDEO_EXT.some((e) => src.toLowerCase().endsWith(e)));

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/* ---------- накладки ---------- */

/**
 * Всё, что появляется поверх видео на время. `at` и `dur` — в секундах
 * от начала сцены: агенту так проще считать, чем в кадрах.
 */
export type Overlay =
  | { kind: "punch"; at: number; dur: number; line1: string; line2?: string }
  | { kind: "offer"; at: number; dur: number; price: string; oldPrice?: string; note?: string; bottom?: number }
  | { kind: "pointer"; at: number; dur: number; x: number; y: number; label?: string; from?: "left" | "right" | "top" | "bottom" }
  | { kind: "step"; at: number; dur: number; n: number; text?: string; top?: number }
  | { kind: "quote"; at: number; dur: number; text: string; author?: string; top?: number }
  | { kind: "count"; at: number; dur: number; to: number; suffix?: string; label?: string; top?: number }
  | { kind: "name"; at: number; dur: number };

/** Как сцена входит в кадр. Резкая склейка — по умолчанию, она честнее. */
export type Enter = "cut" | "fade" | "zoom" | "whip" | "slide";

type Common = {
  /** длительность в кадрах; либо задать `sec` в секундах */
  dur?: number;
  sec?: number;
  enter?: Enter;
  overlays?: Overlay[];
  /** зумы по смыслу: [секунда, масштаб] */
  zooms?: [number, number][];
  captions?: boolean;
};

export type Scene = Common &
  (
    | {
        type: "hook";
        title?: string;
        subtitle?: string;
        src?: string;
        isVideo?: boolean;
        in?: number;
        mute?: boolean;
        volume?: number;
        pan?: [number, number];
      }
    | {
        type: "clip";
        src: string;
        /** с какой секунды исходника берём кусок */
        in?: number;
        speed?: number;
        mute?: boolean;
        volume?: number;
        label?: string;
        fit?: "cover" | "contain";
        /**
         * Сдвиг кадра в долях от его размера: [-0.1, 0] уводит картинку
         * влево, [0, -0.12] — вверх. Вместе с зумом это единственный способ
         * убрать из кадра чужие вшитые субтитры: в готовых рилсах они стоят
         * на разной высоте, и обрезать их одним кропом на весь ролик нельзя.
         */
        pan?: [number, number];
        /**
         * Закрыть полосу кадра — там, где сдвигом чужой текст не убрать.
         * `y` и `h` в долях высоты: {y: 0.62, h: 0.16} прячет полосу
         * с 62% до 78%. По умолчанию матовое стекло, а не глухая заливка:
         * заплатка в кадре заметна сразу, размытие читается как приём.
         */
        cover?: { y: number; h: number; solid?: boolean };
      }
    | { type: "speaker"; nameAt?: number; nameDur?: number; punches?: Punchline[] }
    | { type: "broll"; src: string; isVideo?: boolean; in?: number; label?: string }
    | { type: "compare"; before: Side; after: Side; at?: number; wipe?: number; axis?: "vertical" | "horizontal" }
    | {
        type: "cta";
        line1: string;
        line2?: string;
        button?: string;
        /** кадр под призывом: клип из материала лучше статичной заставки */
        src?: string;
        isVideo?: boolean;
        in?: number;
        mute?: boolean;
        volume?: number;
        /** артикул товара — покупатель ищет по нему на маркетплейсе */
        sku?: string;
      }
  );

export type Punchline = { at: number; dur: number; line1: string; line2?: string };

export type Sfx = { src: string; at: number; volume?: number };

export type Spec = {
  /** ID задания из таблицы — по нему ролик находит свою строку: M1-K1-ГЕЛ-001 */
  tz_id?: string;
  /** ID самого ролика, если из одного ТЗ их несколько */
  video_id?: string;
  /** артикул товара на маркетплейсе; попадает в финал и в описание */
  article?: string;
  style?: string;
  lang?: Lang;
  fps?: number;
  platform?: Platform;
  /** темп монтажа; не задан — берётся из стиля */
  pacing?: Pacing;
  /** вид анимации субтитров; не задан — берётся из стиля */
  captionAnim?: CaptionAnim;
  captionLift?: number;
  /** основной файл для сцен speaker */
  video?: string;
  background?: string;
  /** озвучка — отдельная дорожка поверх всего */
  voice?: string;
  voiceVolume?: number;
  music?: string;
  musicVolume?: number;
  /** приглушать музыку, пока идёт речь */
  duck?: boolean;
  sfx?: Sfx[];
  brand?: { badge?: string; badgeSrc?: string; name?: string; role?: string };
  scenes: Scene[];
};

/* ---------- длительности ---------- */

export const sceneFrames = (sc: Scene, fps: number) =>
  Math.max(1, Math.round(sc.sec !== undefined ? sc.sec * fps : (sc.dur ?? fps)));

export const totalFrames = (spec: Spec) => {
  const fps = spec.fps ?? 30;
  return spec.scenes.reduce((s, x) => s + sceneFrames(x, fps), 0);
};

/* ---------- вход сцены ---------- */

const enterStyle = (enter: Enter | undefined, frame: number, n: number): React.CSSProperties => {
  if (!enter || enter === "cut") return {};
  const o = interpolate(frame, [0, n], [0, 1], clamp);
  switch (enter) {
    case "fade":
      return { opacity: o };
    case "zoom":
      return { opacity: o, scale: interpolate(frame, [0, n * 1.4], [1.14, 1], { ...clamp, easing: EASE }) };
    case "whip":
      return {
        opacity: o,
        translate: `${interpolate(frame, [0, n], [90, 0], { ...clamp, easing: EASE })}px 0px`,
        filter: `blur(${interpolate(frame, [0, n], [14, 0], clamp)}px)`,
      };
    case "slide":
      return { translate: `0px ${interpolate(frame, [0, n * 1.3], [70, 0], { ...clamp, easing: EASE })}px`, opacity: o };
    default:
      return {};
  }
};

/* ---------- накладки поверх сцены ---------- */

const Overlays: React.FC<{ spec: Spec; list?: Overlay[]; fps: number }> = ({ spec, list, fps }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  if (!list?.length) return null;

  return (
    <>
      {list.map((o, i) => {
        // длительность в кадрах нужна самим накладкам: по ней они плавно
        // уходят, а не пропадают на последнем кадре
        const len = Math.max(1, Math.round(o.dur * fps));
        return (
          <Sequence key={i} from={Math.round(o.at * fps)} durationInFrames={len} layout="none">
            {o.kind === "punch" ? (
              <>
                <Brackets style={st} />
                <Punch line1={o.line1} line2={o.line2} style={st} lang={lang} dur={len} />
              </>
            ) : o.kind === "offer" ? (
              <OfferPlate
                price={o.price}
                oldPrice={o.oldPrice}
                note={o.note}
                style={st}
                lang={lang}
                bottom={o.bottom}
                dur={len}
              />
            ) : o.kind === "pointer" ? (
              <Pointer x={o.x} y={o.y} label={o.label} from={o.from} style={st} lang={lang} dur={len} />
            ) : o.kind === "step" ? (
              <StepBadge n={o.n} text={o.text} top={o.top} style={st} lang={lang} dur={len} />
            ) : o.kind === "quote" ? (
              <QuoteCard text={o.text} author={o.author} top={o.top} style={st} lang={lang} dur={len} />
            ) : o.kind === "count" ? (
              <CountUp to={o.to} suffix={o.suffix} label={o.label} top={o.top} style={st} lang={lang} dur={len} />
            ) : spec.brand?.name ? (
              <NameTitle name={spec.brand.name} role={spec.brand.role} style={st} lang={lang} dur={len} />
            ) : null}
          </Sequence>
        );
      })}
    </>
  );
};

/* ---------- сцена: кусок из файла ---------- */

/**
 * То, ради чего всё переписывалось: берём отрезок конкретного файла и ставим
 * его в нужное место ролика. Пять источников — пять таких сцен подряд.
 */
const Clip: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "clip" }>; fps: number }> = ({ spec, sc, fps }) => {
  const st = getStyle(spec.style);
  const font = useFont(spec.lang ?? "ru");
  const frame = useCurrentFrame();
  const scale = zoomAt(frame, sc.zooms ?? [[0, 1]], fps, getPacing(st, spec.pacing).zoomFrames);

  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      <Video
        src={staticFile(sc.src)}
        trimBefore={sc.in ? Math.round(sc.in * fps) : undefined}
        playbackRate={sc.speed ?? 1}
        volume={sc.mute === false ? (sc.volume ?? 1) : 0}
        objectFit={sc.fit ?? "cover"}
        style={{
          width: "100%",
          height: "100%",
          scale,
          translate: sc.pan
            ? `${sc.pan[0] * DESIGN.w}px ${sc.pan[1] * DESIGN.h}px`
            : undefined,
        }}
      />
      {/* Заглушка поверх чужих субтитров. Ставится до виньетки и до наших
          титров, чтобы наш текст лёг сверху и читался. */}
      {sc.cover ? (
        <div
          style={{
            position: "absolute",
            left: 0,
            width: "100%",
            top: sc.cover.y * DESIGN.h,
            height: sc.cover.h * DESIGN.h,
            background: sc.cover.solid ? st.ink : "rgba(0,0,0,.3)",
            backdropFilter: sc.cover.solid ? undefined : "blur(24px) saturate(.9)",
          }}
        />
      ) : null}
      <Vignette style={st} />
      {sc.label ? (
        <div
          style={{
            position: "absolute",
            // под бейджем: оба стоят слева сверху и иначе наезжают друг на друга
            top: topLine(spec.platform ?? "multi", DESIGN.h) + 128,
            left: 34,
            fontFamily: font,
            fontWeight: 900,
            fontSize: 26,
            letterSpacing: 2,
            color: st.ink,
            background: st.accent,
            padding: "7px 16px",
            borderRadius: 6,
            opacity: interpolate(frame, [0, 10], [0, 1], clamp),
          }}
        >
          {sc.label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ---------- сцена: хук ---------- */

/**
 * Хук — первые полторы секунды, на которых зритель решает, листать или нет.
 * Поэтому по умолчанию это кадр из материала с титром поверх, а не заставка
 * с логотипом: заставка съедает ровно те секунды, которые решают всё.
 */
const Hook: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "hook" }>; fps: number }> = ({ spec, sc, fps }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const scale = zoomAt(frame, sc.zooms ?? [[0, 1]], fps, getPacing(st, spec.pacing).zoomFrames);

  const bg = sc.src ?? spec.background;

  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      {bg ? (
        sc.isVideo ?? looksLikeVideo(sc.src) ? (
          <Video
            src={staticFile(bg)}
            trimBefore={sc.in ? Math.round(sc.in * fps) : undefined}
            // на хуке звук исходника часто и есть половина эффекта:
            // звон ложки, льющаяся вода, шорох ткани
            volume={sc.mute === false ? (sc.volume ?? 1) : 0}
            objectFit="cover"
            style={{
              width: "100%",
              height: "100%",
              scale,
              translate: sc.pan ? `${sc.pan[0] * DESIGN.w}px ${sc.pan[1] * DESIGN.h}px` : undefined,
            }}
          />
        ) : (
          <Img
            src={staticFile(bg)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              scale: interpolate(frame, [0, 75], [1.14, 1], { extrapolateRight: "clamp", easing: EASE }),
              filter: "brightness(.62)",
            }}
          />
        )
      ) : null}

      {sc.title ? (
        <div
          style={{
            position: "absolute",
            top: 300,
            width: "100%",
            textAlign: "center",
            padding: "0 34px",
            boxSizing: "border-box",
            fontFamily: font,
            fontWeight: 900,
            fontSize: 84,
            lineHeight: 1.02,
            letterSpacing: 1,
            color: st.textOn,
            textTransform: "uppercase",
            WebkitTextStroke: `9px ${st.ink}`,
            paintOrder: "stroke fill",
            opacity: interpolate(frame, [0, 6], [0, 1], clamp),
            scale: interpolate(frame, [0, 14], [1.22, 1], { ...clamp, easing: EASE }),
          }}
        >
          {sc.title}
        </div>
      ) : null}

      {sc.subtitle ? (
        <div style={{ position: "absolute", top: 500, left: 0, width: "100%", display: "flex", justifyContent: "center" }}>
          <div
            style={{
              background: st.accent,
              color: st.ink,
              fontFamily: font,
              fontWeight: 900,
              fontSize: 32,
              letterSpacing: 2,
              padding: "12px 30px",
              borderRadius: 10,
              opacity: interpolate(frame, [10, 20], [0, 1], clamp),
              translate: `0px ${interpolate(frame, [10, 24], [22, 0], { ...clamp, easing: EASE })}px`,
            }}
          >
            {sc.subtitle}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ---------- сцена: говорящий ---------- */

const Speaker: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "speaker" }>; fps: number }> = ({ spec, sc, fps }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const frame = useCurrentFrame();
  const scale = zoomAt(frame, sc.zooms ?? [[0, 1]], fps, getPacing(st, spec.pacing).zoomFrames);

  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      {spec.video ? (
        <Video src={staticFile(spec.video)} objectFit="cover" style={{ width: "100%", height: "100%", scale }} />
      ) : null}
      <Bokeh style={st} />
      <Vignette style={st} />

      {(sc.punches ?? []).map((p, i) => (
        <Sequence key={i} from={Math.round(p.at * fps)} durationInFrames={p.dur} layout="none">
          <>
            <Brackets style={st} />
            <Punch line1={p.line1} line2={p.line2} style={st} lang={lang} dur={p.dur} />
          </>
        </Sequence>
      ))}

      {sc.nameAt !== undefined && spec.brand?.name ? (
        <Sequence from={Math.round(sc.nameAt * fps)} durationInFrames={sc.nameDur ?? 150} layout="none">
          <NameTitle name={spec.brand.name} role={spec.brand.role} style={st} lang={lang} dur={sc.nameDur ?? 150} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};

/* ---------- сцена: B-roll ---------- */

const Broll: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "broll" }>; fps: number }> = ({ spec, sc, fps }) => {
  const st = getStyle(spec.style);
  const font = useFont(spec.lang ?? "ru");
  const frame = useCurrentFrame();
  const s = interpolate(frame, [0, 90], [1, 1.06], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      {sc.isVideo ? (
        <Video
          src={staticFile(sc.src)}
          trimBefore={sc.in ? Math.round(sc.in * fps) : undefined}
          volume={0}
          objectFit="cover"
          style={{ width: "100%", height: "100%", scale: s }}
        />
      ) : (
        <Img src={staticFile(sc.src)} style={{ width: "100%", height: "100%", objectFit: "cover", scale: s }} />
      )}
      <Vignette style={st} />
      {sc.label ? (
        <div
          style={{
            position: "absolute",
            // под бейджем: оба стоят слева сверху и иначе наезжают друг на друга
            top: topLine(spec.platform ?? "multi", DESIGN.h) + 128,
            left: 34,
            fontFamily: font,
            fontWeight: 900,
            fontSize: 26,
            letterSpacing: 2,
            color: st.ink,
            background: st.accent,
            padding: "7px 16px",
            borderRadius: 6,
            opacity: interpolate(frame, [0, 10], [0, 1], clamp),
          }}
        >
          {sc.label}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ---------- сцена: CTA ---------- */

const Cta: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "cta" }>; fps: number }> = ({ spec, sc, fps }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const pulse = interpolate(frame % 30, [0, 15, 30], [1, 1.05, 1], { easing: EASE });

  const bg = sc.src ?? spec.background;
  const bgIsVideo = sc.src ? (sc.isVideo ?? looksLikeVideo(sc.src)) : false;

  const skuText = `${SKU_LABEL[lang]} ${sc.sku ?? ""}`;
  // 60 — горизонтальные поля плашки, 48 — зазор до краёв кадра
  const skuSize = fitFontSize(skuText, font, 900, 56, DESIGN.w - 48 - 60);

  return (
    <AbsoluteFill style={{ background: st.ink }}>
      {/* Под призывом лучше работающий товар, а не заставка: статичный финал
          и удержание роняет, и проверка ловит его как замерший кадр.
          Картинка остаётся запасным вариантом и едет наездом. */}
      {bg ? (
        bgIsVideo ? (
          <Video
            src={staticFile(bg)}
            trimBefore={sc.in ? Math.round(sc.in * fps) : undefined}
            volume={sc.mute === false ? (sc.volume ?? 1) : 0}
            objectFit="cover"
            style={{ width: "100%", height: "100%", filter: "brightness(.82)" }}
          />
        ) : (
          <Img
            src={staticFile(bg)}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              filter: "brightness(.62)",
              scale: interpolate(frame, [0, 90], [1, 1.18], { extrapolateRight: "clamp", easing: EASE }),
            }}
          />
        )
      ) : null}
      {/* Только градиент под текстом, чтобы буквы читались. Заливать финал
          тёмным на весь кадр нельзя: товар пропадает как раз там, где
          зритель решает, покупать или нет. */}
      <AbsoluteFill
        style={{
          background:
            `linear-gradient(180deg, rgba(0,0,0,.55) 0%, rgba(0,0,0,.12) 34%,` +
            ` rgba(0,0,0,.12) 62%, rgba(0,0,0,.62) 100%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          top: 300,
          width: "100%",
          textAlign: "center",
          scale: interpolate(frame, [0, 12], [2.4, 1], { ...clamp, easing: EASE }),
          opacity: interpolate(frame, [0, 6], [0, 1], clamp),
        }}
      >
        <div
          style={{
            fontFamily: font,
            fontWeight: 900,
            fontSize: 100,
            lineHeight: 0.98,
            color: st.textOn,
            textTransform: "uppercase",
            WebkitTextStroke: `10px ${st.ink}`,
            paintOrder: "stroke fill",
          }}
        >
          {sc.line1}
        </div>
        {sc.line2 ? (
          <div
            style={{
              fontFamily: font,
              fontWeight: 900,
              fontSize: 112,
              lineHeight: 0.98,
              color: st.accent,
              textTransform: "uppercase",
              WebkitTextStroke: `10px ${st.ink}`,
              paintOrder: "stroke fill",
            }}
          >
            {sc.line2}
          </div>
        ) : null}
      </div>
      {/* Артикул: по нему покупатель находит товар на маркетплейсе.
          Два жёстких правила, оба выведены из брака.
          1. Отступ снизу считается от реальной высоты блока субтитров —
             подобранное на глаз число при крупном шрифте давало наложение,
             и цифры пропадали под текстом.
          2. Размер подгоняется под ширину кадра: на 56 пунктах армянская
             строка не помещалась и крайние цифры срезало краем. */}
      {sc.sku ? (
        <div
          style={{
            position: "absolute",
            bottom:
              captionBottom(spec.platform ?? "multi", DESIGN.h, spec.captionLift ?? st.caption.lift) +
              captionBlockHeight(st),
            left: 0,
            width: "100%",
            display: "flex",
            justifyContent: "center",
            opacity: interpolate(frame, [26, 40], [0, 1], clamp),
          }}
        >
          <div
            style={{
              fontFamily: font,
              fontWeight: 900,
              fontSize: skuSize,
              letterSpacing: 1,
              color: st.textOn,
              background: "rgba(0,0,0,.82)",
              border: `4px solid ${st.accent}`,
              padding: "12px 30px",
              borderRadius: 14,
              whiteSpace: "nowrap",
            }}
          >
            {skuText}
          </div>
        </div>
      ) : null}

      {sc.button ? (
        <div style={{ position: "absolute", top: 680, left: 0, width: "100%", display: "flex", justifyContent: "center" }}>
          <div
            style={{
              background: st.accent,
              color: st.ink,
              fontFamily: font,
              fontWeight: 900,
              fontSize: 34,
              letterSpacing: 2,
              padding: "16px 40px",
              borderRadius: 34,
              boxShadow: `0 14px 40px ${st.accent}70`,
              opacity: interpolate(frame, [20, 34], [0, 1], clamp),
              scale: interpolate(frame, [20, 36], [0.76, pulse], { ...clamp, easing: EASE }),
            }}
          >
            {sc.button}
          </div>
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/* ---------- звук ---------- */

/**
 * Музыка приглушается, пока идёт речь. Без этого голос тонет, а зритель
 * уходит — на телефоне в шумном месте разборчивость важнее атмосферы.
 */
const musicVolume = (blocks: KBlock[], base: number, duck: boolean, fps: number) => (f: number) => {
  const t = f / fps;
  if (!duck) return base;
  const speaking = blocks.some((b) => t >= b.start - 0.25 && t <= b.end + 0.35);
  return speaking ? base * 0.35 : base;
};

/* ---------- сборка ---------- */

export const Reel: React.FC<{ spec: Spec; captions: KBlock[] }> = ({ spec, captions }) => {
  const st = getStyle(spec.style);
  const fps = spec.fps ?? 30;
  const lang = spec.lang ?? "ru";
  const platform = spec.platform ?? "multi";

  let at = 0;
  /**
   * Отрезки, на которых субтитры не показываются. На CTA и на хуке с титром
   * уже стоит крупный текст — второй слой поверх него читается как ошибка
   * сборки. Сцена может переопределить это полем `captions`.
   */
  const hidden: [number, number][] = [];
  let cursor = 0;
  for (const sc of spec.scenes) {
    const len = sceneFrames(sc, fps);
    const auto = sc.type === "cta" || (sc.type === "hook" && Boolean(sc.title));
    if (sc.captions === false || (sc.captions === undefined && auto)) {
      hidden.push([cursor / fps, (cursor + len) / fps]);
    }
    cursor += len;
  }

  return (
    <AbsoluteFill style={{ background: st.ink }}>
      {spec.scenes.map((sc, i) => {
        const from = at;
        const len = sceneFrames(sc, fps);
        at += len;

        return (
          <Sequence key={i} from={from} durationInFrames={len}>
            <SceneBody spec={spec} sc={sc} fps={fps} />
          </Sequence>
        );
      })}

      {/* Полоса прогресса — по всему ролику, а не по сцене: она держит
          зрителя обещанием «осталось чуть-чуть», и прогресс отдельной сцены
          вместо общего этот смысл ломает. */}
      <Progress style={st} total={totalFrames(spec)} />

      {/* субтитры и бейдж живут поверх всего монтажа, а не внутри сцен —
          иначе они рвутся на склейках */}
      <Captions
        blocks={captions}
        style={st}
        lang={lang}
        fps={fps}
        anim={spec.captionAnim}
        platform={platform}
        frameHeight={DESIGN.h}
        lift={spec.captionLift ?? st.caption.lift}
        hideDuring={hidden}
      />
      <Badge
        style={st}
        text={spec.brand?.badge}
        src={spec.brand?.badgeSrc}
        platform={platform}
        frameHeight={DESIGN.h}
      />

      {spec.voice ? <Audio src={staticFile(spec.voice)} volume={spec.voiceVolume ?? 1} /> : null}
      {spec.music ? (
        <Audio
          src={staticFile(spec.music)}
          volume={musicVolume(captions, spec.musicVolume ?? 0.07, spec.duck ?? true, fps)}
          loop
        />
      ) : null}
      {(spec.sfx ?? []).map((s, i) => (
        <Sequence key={`sfx${i}`} from={Math.round(s.at * fps)} layout="none">
          <Audio src={staticFile(s.src)} volume={s.volume ?? 0.5} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

/** Тело сцены с анимацией входа и накладками. */
const SceneBody: React.FC<{ spec: Spec; sc: Scene; fps: number }> = ({ spec, sc, fps }) => {
  const frame = useCurrentFrame();
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";

  return (
    <AbsoluteFill style={enterStyle(sc.enter, frame, getPacing(st, spec.pacing).enterFrames)}>
      {sc.type === "hook" ? (
        <Hook spec={spec} sc={sc} fps={fps} />
      ) : sc.type === "clip" ? (
        <Clip spec={spec} sc={sc} fps={fps} />
      ) : sc.type === "speaker" ? (
        <Speaker spec={spec} sc={sc} fps={fps} />
      ) : sc.type === "broll" ? (
        <Broll spec={spec} sc={sc} fps={fps} />
      ) : sc.type === "compare" ? (
        <BeforeAfter
          before={sc.before}
          after={sc.after}
          style={st}
          lang={lang}
          fps={fps}
          at={sc.at ?? 0.6}
          dur={sc.wipe ?? 0.9}
          axis={sc.axis}
        />
      ) : (
        <Cta spec={spec} sc={sc} fps={fps} />
      )}
      <Overlays spec={spec} list={sc.overlays} fps={fps} />
    </AbsoluteFill>
  );
};

/**
 * Обёртка вывода: макет нарисован в 720×1280, кадр отдаём в 1080×1920.
 * Масштабируется вся сцена целиком, поэтому текст остаётся векторным
 * и не мылится — это не апскейл картинки.
 */
export const Stage: React.FC<{ spec: Spec; captions: KBlock[] }> = ({ spec, captions }) => {
  const { width, height } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: getStyle(spec.style).ink }}>
      <AbsoluteFill
        style={{
          width: DESIGN.w,
          height: DESIGN.h,
          transform: `scale(${width / DESIGN.w}, ${height / DESIGN.h})`,
          transformOrigin: "top left",
        }}
      >
        <Reel spec={spec} captions={captions} />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
