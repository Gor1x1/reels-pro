import { Composition } from "remotion";
import { Stage, totalFrames, type Spec } from "./Reel";
import { STYLES } from "./styles";
import { CAPTION_ANIMS } from "./captions/anim";
import spec from "./spec.json";
import captions from "./captions.json";
import type { KBlock } from "./kit/Kit";

const S = spec as unknown as Spec;
const C = captions as unknown as KBlock[];

/** Кадр вывода. Проверка качества требует ровно этот размер. */
const W = 1080;
const H = 1920;

export const RemotionRoot: React.FC = () => (
  <>
    {/* основная сборка по спецификации */}
    <Composition
      id="Reel"
      component={Stage}
      durationInFrames={totalFrames(S)}
      fps={S.fps ?? 30}
      width={W}
      height={H}
      defaultProps={{ spec: S, captions: C }}
    />

    {/* тот же ролик в каждом стиле — для сравнения */}
    {Object.values(STYLES).map((st) => (
      <Composition
        key={st.id}
        id={`Style-${st.id}`}
        component={Stage}
        durationInFrames={totalFrames(S)}
        fps={S.fps ?? 30}
        width={W}
        height={H}
        defaultProps={{ spec: { ...S, style: st.id }, captions: C }}
      />
    ))}

    {/* каждая анимация субтитров отдельной композицией — выбирать глазами,
        а не по названию в списке */}
    {CAPTION_ANIMS.map((a) => (
      <Composition
        key={a}
        id={`Caption-${a}`}
        component={Stage}
        durationInFrames={Math.min(totalFrames(S), (S.fps ?? 30) * 8)}
        fps={S.fps ?? 30}
        width={W}
        height={H}
        defaultProps={{ spec: { ...S, captionAnim: a }, captions: C }}
      />
    ))}
  </>
);
