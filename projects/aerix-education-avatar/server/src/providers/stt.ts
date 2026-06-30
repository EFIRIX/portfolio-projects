import OpenAI, { toFile } from 'openai';
import { createClient as createDeepgram } from '@deepgram/sdk';
import { config } from '../config';

export interface STTResult {
  text: string;
  confidence?: number;
}

export interface STTProvider {
  transcribe(buffer: Buffer, sampleRate: number, abortSignal?: AbortSignal): Promise<STTResult>;
}

class OpenAIWhisperProvider implements STTProvider {
  private client = new OpenAI({ apiKey: config.openaiApiKey });
  async transcribe(buffer: Buffer, sampleRate: number, abortSignal?: AbortSignal): Promise<STTResult> {
    const transcription = await this.client.audio.transcriptions.create(
      {
        file: await toFile(buffer, 'audio.pcm'),
        model: 'whisper-1',
        language: 'en',
        response_format: 'verbose_json',
        temperature: 0,
        prompt: ''
      },
      { signal: abortSignal }
    );
    const text = (transcription as any)?.text ?? '';
    const confidence = (transcription as any)?.confidence ?? undefined;
    return { text, confidence };
  }
}

class DeepgramSTTProvider implements STTProvider {
  private client = createDeepgram(config.deepgramApiKey as string);
  async transcribe(buffer: Buffer, sampleRate: number, abortSignal?: AbortSignal): Promise<STTResult> {
    const response = await this.client.listen.prerecorded.transcribeFile(buffer, {
      model: 'nova-2-conversationalai',
      smart_format: true,
      punctuate: true,
      language: 'en',
      sample_rate: sampleRate
    });
    const alt = response.result?.results?.channels?.[0]?.alternatives?.[0];
    return {
      text: alt?.transcript ?? '',
      confidence: alt?.confidence
    };
  }
}

class MockSTTProvider implements STTProvider {
  async transcribe(buffer: Buffer): Promise<STTResult> {
    return { text: `user spoke (${Math.round(buffer.length / 1024)}KB audio)` };
  }
}

export function buildSTTProvider(): STTProvider {
  if (config.openaiApiKey) return new OpenAIWhisperProvider();
  if (config.deepgramApiKey) return new DeepgramSTTProvider();
  return new MockSTTProvider();
}
