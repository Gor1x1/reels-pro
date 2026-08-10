import { Composition } from "remotion";
import { Reel, totalFrames, type Spec } from "./Reel";
import { STYLES } from "./styles";
import spec from "./spec.json";
import captions from "./captions.json";
import type { KBlock } from "./kit/Kit";

const S = spec as unknown as Spec;
const C = captions as unknown as KBlock[];

export const RemotionRoot: React.FC = () => (
  <>
    {/* основная сборка по спецификации */}
    <Composition
      id="Reel"
      component={Reel}
      durationInFrames={totalFrames(S)}
      fps={S.fps ?? 30}
      width={720}
      height={1280}
      defaultProps={{ spec: S, captions: C }}
    />
    {/* тот же ролик в каждом стиле — для сравнения */}
    {Object.values(STYLES).map((st) => (
      <Composition
        key={st.id}
        id={`Style-${st.id}`}
        component={Reel}
        durationInFrames={totalFrames(S)}
        fps={S.fps ?? 30}
        width={720}
        height={1280}
        defaultProps={{ spec: { ...S, style: st.id }, captions: C }}
      />
    ))}
  </>
);
