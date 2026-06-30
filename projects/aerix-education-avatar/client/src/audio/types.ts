export interface AnimationPayload {
  version: string;
  phonemes: { id: string; start_ms: number; end_ms: number }[];
  visemes: { id: string; weight: number }[];
  blendshapes: Record<string, number>;
  emotion: 'neutral' | 'happy' | 'serious';
  head: { yaw: number; pitch: number };
  eyes: { blink: boolean; gaze: [number, number, number] };
}
