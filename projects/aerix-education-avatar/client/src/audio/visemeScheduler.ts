import { AnimationPayload } from './types';

// ARKit-aligned viseme/blendshape mapping (Ready Player Me rigs)
const VISEME_MAP: Record<string, { blendshape: string; weight: number }> = {
  AA: { blendshape: 'jawOpen', weight: 0.75 },
  AE: { blendshape: 'mouthStretch', weight: 0.7 },
  AH: { blendshape: 'jawOpen', weight: 0.6 },
  AO: { blendshape: 'mouthFunnel', weight: 0.7 },
  EH: { blendshape: 'mouthStretch', weight: 0.6 },
  ER: { blendshape: 'mouthPucker', weight: 0.55 },
  EY: { blendshape: 'mouthSmile_L', weight: 0.45 },
  IH: { blendshape: 'jawOpen', weight: 0.35 },
  IY: { blendshape: 'mouthClose', weight: 0.4 },
  OW: { blendshape: 'mouthFunnel', weight: 0.8 },
  UH: { blendshape: 'mouthClose', weight: 0.3 },
  UW: { blendshape: 'mouthFunnel', weight: 0.65 },
  P: { blendshape: 'mouthClose', weight: 0.9 },
  S: { blendshape: 'mouthDimple_L', weight: 0.5 },
  T: { blendshape: 'mouthClose', weight: 0.4 },
  V: { blendshape: 'mouthFunnel', weight: 0.5 },
  W: { blendshape: 'mouthFunnel', weight: 0.5 },
  CH: { blendshape: 'jawOpen', weight: 0.55 },
  SH: { blendshape: 'jawOpen', weight: 0.45 },
  TH: { blendshape: 'jawOpen', weight: 0.4 },
  V3: { blendshape: 'jawOpen', weight: 0.8 }
};

const EMOTION_PRESET: Record<string, Partial<BlendshapeState>> = {
  neutral: {},
  happy: { mouthSmile_L: 0.35, mouthSmile_R: 0.35, eyeSquint_L: 0.1, eyeSquint_R: 0.1 },
  serious: { browDown_L: 0.3, browDown_R: 0.3, mouthPress_L: 0.2, mouthPress_R: 0.2 }
};

export type BlendshapeState = Record<string, number>;

export class VisemeScheduler {
  constructor(
    private setBlendshapes: (blend: BlendshapeState, emotion: string) => void,
    private getAudioClock: () => number
  ) {}

  schedule(payload: AnimationPayload) {
    const now = this.getAudioClock();
    const firstPhoneme = payload.phonemes[0];
    const delay = firstPhoneme ? firstPhoneme.start_ms / 1000 : 0;
    const targetTime = now + delay;
    const run = () => {
      const blend: BlendshapeState = { ...payload.blendshapes };
      payload.visemes.forEach((v) => {
        const map = VISEME_MAP[v.id];
        if (map) blend[map.blendshape] = v.weight;
      });
      const emotionBlend = EMOTION_PRESET[payload.emotion] ?? {};
      Object.entries(emotionBlend).forEach(([k, v]) => {
        blend[k] = Math.max(blend[k] ?? 0, v as number);
      });
      this.setBlendshapes(blend, payload.emotion);
    };
    const deltaMs = Math.max(0, (targetTime - this.getAudioClock()) * 1000);
    window.setTimeout(run, deltaMs);
  }
}
