export interface SessionState {
  sessionId: string;
  personaId: string;
  subject: string;
  history: string[];
  level: string;
  context?: string;
}

export interface AnimationPayload {
  version: string;
  phonemes: { id: string; start_ms: number; end_ms: number }[];
  visemes: { id: string; weight: number }[];
  blendshapes: Record<string, number>;
  emotion: 'neutral' | 'happy' | 'serious';
  head: { yaw: number; pitch: number };
  eyes: { blink: boolean; gaze: [number, number, number] };
}

export interface AudioStreamMessage {
  type: 'start' | 'audio_chunk' | 'interrupt';
  sessionId?: string;
  personaId?: string;
  sampleRate?: number;
  format?: 'pcm16' | 'opus';
  data?: string; // base64 audio chunk when type === 'audio_chunk'
}

export interface ServerMessage {
  type: 'ack' | 'response_meta' | 'tts_chunk' | 'animation' | 'error' | 'stopped';
  turnId?: string;
  text?: string;
  emotion?: AnimationPayload['emotion'];
  level?: string;
  chunk?: string; // base64
  timestamp?: number;
  done?: boolean;
  payload?: AnimationPayload;
  message?: string;
}
