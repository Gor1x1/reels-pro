/**
 * Ролик собирается из спецификации (spec.json), а не пишется руками.
 * Меняешь "style" — меняется весь внешний вид, монтаж остаётся тем же.
 */
import { AbsoluteFill, Img, Sequence, staticFile, useCurrentFrame, interpolate } from "remotion";
import { Video, Audio } from "@remotion/media";
import { getStyle, type Lang } from "./styles";
import {
  Badge,
  Bokeh,
  Brackets,
  Captions,
  EASE,
  NameTitle,
  Progress,
  Punch,
  Vignette,
  useFont,
  zoomAt,
  type KBlock,
} from "./kit/Kit";

export type Punchline = { at: number; dur: number; line1: string; line2?: string };

export type Scene =
  | { type: "hook"; dur: number; title: string; subtitle?: string }
  | {
      type: "speaker";
      dur: number;
      zooms?: [number, number][];
      punches?: Punchline[];
      nameAt?: number;
      nameDur?: number;
    }
  | { type: "broll"; dur: number; src: string; isVideo?: boolean; label?: string }
  | { type: "cta"; dur: number; line1: string; line2?: string; button?: string };

export type Spec = {
  style?: string;
  lang?: Lang;
  fps?: number;
  video: string;
  background?: string;
  music?: string;
  musicVolume?: number;
  brand?: { badge?: string; badgeSrc?: string; name?: string; role?: string };
  scenes: Scene[];
};

/* ---------- сцена: хук ---------- */
const Hook: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "hook" }> }> = ({ spec, sc }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const font = useFont(lang);
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: st.ink }}>
      {spec.background ? (
        <Img
          src={staticFile(spec.background)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            scale: interpolate(frame, [0, 75], [1.14, 1], { extrapolateRight: "clamp", easing: EASE }),
            filter: "brightness(.55)",
          }}
        />
      ) : null}
      <AbsoluteFill style={{ background: `linear-gradient(180deg, ${st.ink}66, ${st.ink}e0)` }} />
      <Bokeh style={st} />
      <div
        style={{
          position: "absolute",
          top: 470,
          width: "100%",
          textAlign: "center",
          fontFamily: font,
          fontWeight: 900,
          fontSize: 126,
          letterSpacing: 3,
          color: st.textOn,
          WebkitTextStroke: `9px ${st.ink}`,
          paintOrder: "stroke fill",
          opacity: interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" }),
          scale: interpolate(frame, [0, 18], [1.45, 1], { extrapolateRight: "clamp", easing: EASE }),
        }}
      >
        {sc.title}
      </div>
      {sc.subtitle ? (
        <div style={{ position: "absolute", top: 620, left: 0, width: "100%", display: "flex", justifyContent: "center" }}>
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
              opacity: interpolate(frame, [16, 28], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
              translate: interpolate(frame, [16, 32], ["0px 22px", "0px 0px"], {
                extrapolateRight: "clamp",
                extrapolateLeft: "clamp",
                easing: EASE,
              }),
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
const Speaker: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "speaker" }>; captions: KBlock[] }> = ({
  spec,
  sc,
  captions,
}) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const fps = spec.fps ?? 30;
  const frame = useCurrentFrame();
  const scale = zoomAt(frame, sc.zooms ?? [[0, 1]], fps, st);

  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      <Video src={staticFile(spec.video)} style={{ width: "100%", height: "100%", objectFit: "cover", scale }} />
      <Bokeh style={st} />
      <Vignette style={st} />
      <Progress style={st} total={sc.dur} />

      {(sc.punches ?? []).map((p, i) => (
        <Sequence key={i} from={Math.round(p.at * fps)} durationInFrames={p.dur} layout="none">
          <>
            <Brackets style={st} />
            <Punch line1={p.line1} line2={p.line2} style={st} lang={lang} />
          </>
        </Sequence>
      ))}

      {sc.nameAt !== undefined && spec.brand?.name ? (
        <Sequence from={Math.round(sc.nameAt * fps)} durationInFrames={sc.nameDur ?? 150} layout="none">
          <NameTitle name={spec.brand.name} role={spec.brand.role} style={st} lang={lang} dur={sc.nameDur ?? 150} />
        </Sequence>
      ) : null}

      <Captions blocks={captions} style={st} lang={lang} fps={fps} />
      <Badge style={st} text={spec.brand?.badge} src={spec.brand?.badgeSrc} />
    </AbsoluteFill>
  );
};

/* ---------- сцена: B-roll ---------- */
const Broll: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "broll" }> }> = ({ spec, sc }) => {
  const st = getStyle(spec.style);
  const font = useFont(spec.lang ?? "ru");
  const frame = useCurrentFrame();
  const s = interpolate(frame, [0, 90], [1, 1.06], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ background: st.ink, overflow: "hidden" }}>
      {sc.isVideo ? (
        <Video src={staticFile(sc.src)} style={{ width: "100%", height: "100%", objectFit: "cover", scale: s }} />
      ) : (
        <Img src={staticFile(sc.src)} style={{ width: "100%", height: "100%", objectFit: "cover", scale: s }} />
      )}
      <Vignette style={st} />
      {sc.label ? (
        <div
          style={{
            position: "absolute",
            top: 44,
            left: 34,
            fontFamily: font,
            fontWeight: 900,
            fontSize: 26,
            letterSpacing: 2,
            color: st.ink,
            background: st.accent,
            padding: "7px 16px",
            borderRadius: 6,
            opacity: interpolate(frame, [0, 10], [0, 1], { extrapolateRight: "clamp" }),
          }}
        >
          {sc.label}
        </div>
      ) : null}
      <Badge style={st} text={spec.brand?.badge} src={spec.brand?.badgeSrc} />
    </AbsoluteFill>
  );
};

/* ---------- сцена: CTA ---------- */
const Cta: React.FC<{ spec: Spec; sc: Extract<Scene, { type: "cta" }> }> = ({ spec, sc }) => {
  const st = getStyle(spec.style);
  const lang = spec.lang ?? "ru";
  const font = useFont(lang);
  const frame = useCurrentFrame();
  const pulse = interpolate(frame % 30, [0, 15, 30], [1, 1.05, 1], { easing: EASE });
  return (
    <AbsoluteFill style={{ background: st.ink }}>
      {spec.background ? (
        <Img src={staticFile(spec.background)} style={{ width: "100%", height: "100%", objectFit: "cover", filter: "brightness(.42) blur(2px)" }} />
      ) : null}
      <AbsoluteFill style={{ background: `radial-gradient(circle at 50% 44%, ${st.accent}30 0%, ${st.ink}ee 62%)` }} />
      <Bokeh style={st} />
      <div
        style={{
          position: "absolute",
          top: 300,
          width: "100%",
          textAlign: "center",
          scale: interpolate(frame, [0, 12], [2.4, 1], { extrapolateRight: "clamp", easing: EASE }),
          opacity: interpolate(frame, [0, 6], [0, 1], { extrapolateRight: "clamp" }),
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
              opacity: interpolate(frame, [20, 34], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" }),
              scale: interpolate(frame, [20, 36], [0.76, pulse], {
                extrapolateRight: "clamp",
                extrapolateLeft: "clamp",
                easing: EASE,
              }),
            }}
          >
            {sc.button}
          </div>
        </div>
      ) : null}
      <Badge style={st} text={spec.brand?.badge} src={spec.brand?.badgeSrc} />
    </AbsoluteFill>
  );
};

/* ---------- сборка ---------- */
export const Reel: React.FC<{ spec: Spec; captions: KBlock[] }> = ({ spec, captions }) => {
  const st = getStyle(spec.style);
  let at = 0;
  return (
    <AbsoluteFill style={{ background: st.ink }}>
      {spec.scenes.map((sc, i) => {
        const from = at;
        at += sc.dur;
        return (
          <Sequence key={i} from={from} durationInFrames={sc.dur}>
            {sc.type === "hook" ? (
              <Hook spec={spec} sc={sc} />
            ) : sc.type === "speaker" ? (
              <Speaker spec={spec} sc={sc} captions={captions} />
            ) : sc.type === "broll" ? (
              <Broll spec={spec} sc={sc} />
            ) : (
              <Cta spec={spec} sc={sc} />
            )}
          </Sequence>
        );
      })}
      {spec.music ? <Audio src={staticFile(spec.music)} volume={spec.musicVolume ?? 0.07} loop /> : null}
    </AbsoluteFill>
  );
};

export const totalFrames = (spec: Spec) => spec.scenes.reduce((s, x) => s + x.dur, 0);
