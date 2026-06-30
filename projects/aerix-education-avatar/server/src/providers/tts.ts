import OpenAI from 'openai';
import { config } from '../config';

export interface TTSProvider {
  stream(text: string, options: { abortSignal?: AbortSignal; sampleRate: number }): AsyncGenerator<Buffer>;
}

class OpenAITTSProvider implements TTSProvider {
  private client = new OpenAI({ apiKey: config.openaiApiKey });
  async *stream(text: string, options: { abortSignal?: AbortSignal; sampleRate: number }) {
    const response = await this.client.audio.speech.create({
      model: config.ttsModel,
      voice: config.ttsVoice,
      input: text,
      format: 'pcm',
      sample_rate: options.sampleRate,
      stream: true
    }, { signal: options.abortSignal });

    const reader = response.body?.getReader();
    if (!reader) return;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (value) yield Buffer.from(value);
    }
  }
}

class MockTTSProvider implements TTSProvider {
  async *stream(text: string, options: { sampleRate: number }) {
    const durationMs = 500;
    const sampleCount = Math.floor(options.sampleRate * (durationMs / 1000));
    const buffer = Buffer.alloc(sampleCount * 2);
    for (let i = 0; i < sampleCount; i++) {
      const t = i / options.sampleRate;
      const sample = Math.sin(2 * Math.PI * 220 * t);
      const intSample = Math.max(-1, Math.min(1, sample)) * 32767;
      buffer.writeInt16LE(intSample, i * 2);
    }
    yield buffer;
  }
}

export function buildTTSProvider(): TTSProvider {
  if (config.openaiApiKey) return new OpenAITTSProvider();
  return new MockTTSProvider();
}
