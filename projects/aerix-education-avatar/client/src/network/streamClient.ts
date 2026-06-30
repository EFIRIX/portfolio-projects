import { AnimationPayload } from '../audio/types';

export type ClientEvent =
  | { type: 'opened' }
  | { type: 'ack'; timestamp: number }
  | { type: 'response_meta'; turnId: string; text: string; emotion: string; level: string }
  | { type: 'tts_chunk'; turnId: string; chunk?: string; timestamp?: number; done?: boolean }
  | { type: 'animation'; turnId: string; payload: AnimationPayload }
  | { type: 'error'; message: string }
  | { type: 'stopped'; turnId?: string };

export interface StreamClientOptions {
  url?: string;
}

export class StreamClient {
  private ws?: WebSocket;
  private listeners: ((ev: ClientEvent) => void)[] = [];
  private url: string;

  constructor(opts?: StreamClientOptions) {
    this.url = opts?.url ?? `${window.location.origin.replace(/^http/, 'ws')}/api/stream/audio`;
  }

  on(listener: (ev: ClientEvent) => void) {
    this.listeners.push(listener);
  }

  private emit(ev: ClientEvent) {
    this.listeners.forEach((l) => l(ev));
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.onopen = () => this.emit({ type: 'opened' });
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data.toString());
        this.emit(msg as ClientEvent);
      } catch (e) {
        this.emit({ type: 'error', message: 'invalid JSON' });
      }
    };
    this.ws.onerror = () => this.emit({ type: 'error', message: 'socket error' });
  }

  start(sessionId: string, sampleRate = 16000) {
    this.ws?.send(JSON.stringify({ type: 'start', sessionId, sampleRate, format: 'pcm16' }));
  }

  sendAudioChunk(data: ArrayBuffer) {
    const b64 = btoa(String.fromCharCode(...new Uint8Array(data)));
    this.ws?.send(JSON.stringify({ type: 'audio_chunk', data: b64 }));
  }

  interrupt() {
    this.ws?.send(JSON.stringify({ type: 'interrupt' }));
  }
}
