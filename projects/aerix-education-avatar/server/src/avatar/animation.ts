import { AnimationPayload } from '../types';

const defaultViseme: AnimationPayload['visemes'][number] = { id: 'V3', weight: 0.8 };

export function buildAnimationPayload(text: string, emotion: AnimationPayload['emotion']): AnimationPayload {
  return {
    version: '1.0',
    phonemes: [
      { id: 'AA', start_ms: 0, end_ms: 120 },
      { id: 'M', start_ms: 120, end_ms: 240 }
    ],
    visemes: [defaultViseme],
    blendshapes: { mouthOpen: 0.6, smile: emotion === 'happy' ? 0.4 : 0.1 },
    emotion,
    head: { yaw: 0.05, pitch: -0.02 },
    eyes: { blink: false, gaze: [0, 0, 1] }
  };
}
