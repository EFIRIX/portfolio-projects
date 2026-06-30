import { SocketStream } from '@fastify/websocket';
import { v4 as uuidv4 } from 'uuid';
import { SessionState, ServerMessage, AnimationPayload } from './types';
import { buildSTTProvider } from './providers/stt';
import { buildLLMProvider } from './providers/llm';
import { buildTTSProvider } from './providers/tts';
import { buildAnimationPayload } from './avatar/animation';
import { violatesPolicy } from './policy';
import { SessionStore } from './persistence/sessionStore';
import { recordMetrics } from './metrics';

const sttProvider = buildSTTProvider();
const llmProvider = buildLLMProvider();
const ttsProvider = buildTTSProvider();

interface TurnOptions {
  ws: SocketStream;
  session: SessionState;
  audioBuffer: Buffer;
  sampleRate: number;
  abortFlag: { controller: AbortController };
  sessionStore: SessionStore;
}

export async function handleTurn(options: TurnOptions) {
  const { ws, session, audioBuffer, sampleRate, abortFlag, sessionStore } = options;
  const turnStart = Date.now();
  const controller = abortFlag.controller;

  // --- STT ---
  const sttStarted = Date.now();
  const sttResult = await sttProvider.transcribe(audioBuffer, sampleRate, controller.signal);
  const sttLatency = Date.now() - sttStarted;

  if (controller.signal.aborted) return;

  if (violatesPolicy(sttResult.text)) {
    ws.socket.send(JSON.stringify({ type: 'error', message: 'restricted_content' } satisfies ServerMessage));
    return;
  }

  // --- LLM streaming ---
  const turnId = uuidv4();
  let fullText = '';
  let metaSent = false;
  const animationEmotion: AnimationPayload['emotion'] = 'neutral';
  let llmFirstTokenMs: number | null = null;
  let ttsFirstChunkMs: number | null = null;
  let ttsStartTs: number | null = null;
  let ttsEndTs: number | null = null;

  // Helper to stream TTS for a segment of text
  const streamSegment = async (segment: string, isLastSegment: boolean) => {
    if (segment.trim().length === 0) return;
    const ttsStream = ttsProvider.stream(segment, { sampleRate, abortSignal: controller.signal });
    if (ttsStartTs === null) ttsStartTs = Date.now();
    for await (const audioChunk of ttsStream) {
      if (controller.signal.aborted) return;
      if (ttsFirstChunkMs === null) {
        ttsFirstChunkMs = Date.now() - turnStart;
      }
      const msg: ServerMessage = {
        type: 'tts_chunk',
        turnId,
        chunk: audioChunk.toString('base64'),
        timestamp: Date.now(),
        done: false
      };
      ws.socket.send(JSON.stringify(msg));
    }
    ttsEndTs = Date.now();
    if (isLastSegment && !controller.signal.aborted) {
      ws.socket.send(JSON.stringify({ type: 'tts_chunk', turnId, done: true, timestamp: Date.now() } satisfies ServerMessage));
    }
  };

  const systemPrompt = `You are an AI teacher with persona ${session.personaId}. Keep responses concise.`;
  const userMessage = sttResult.text || 'Hello';
  const messages = [
    { role: 'system' as const, content: systemPrompt },
    { role: 'user' as const, content: userMessage }
  ];

  let buffer = '';
  const llmStream = llmProvider.streamCompletion({ messages, abortSignal: controller.signal });

  for await (const token of llmStream) {
    if (controller.signal.aborted) return;
    if (!metaSent) {
      const responseMeta: ServerMessage = {
        type: 'response_meta',
        turnId,
        text: '',
        emotion: animationEmotion,
        level: session.level,
        timestamp: Date.now()
      };
      ws.socket.send(JSON.stringify(responseMeta));
      metaSent = true;
    }
    if (llmFirstTokenMs === null) {
      llmFirstTokenMs = Date.now() - turnStart;
    }
    fullText += token;
    buffer += token;
    // Flush on punctuation or buffer size threshold
    if (/[\.\!\?]/.test(token) || buffer.length > 80) {
      const seg = buffer;
      buffer = '';
      await streamSegment(seg, false);
    }
  }

  if (buffer.length > 0) {
    await streamSegment(buffer, true);
  } else {
    // mark done if last segment already emitted as done
    ws.socket.send(JSON.stringify({ type: 'tts_chunk', turnId, done: true, timestamp: Date.now() } satisfies ServerMessage));
  }

  if (controller.signal.aborted) return;

  const animation = buildAnimationPayload(fullText, animationEmotion);
  ws.socket.send(JSON.stringify({ type: 'animation', turnId, payload: animation, timestamp: Date.now() } satisfies ServerMessage));

  // Update session history
  session.history = [...session.history, userMessage, fullText].slice(-20);

  const now = Date.now();
  recordMetrics({
    stt_ms: sttLatency,
    llm_first_token_ms: llmFirstTokenMs ?? 0,
    tts_first_chunk_ms: ttsFirstChunkMs ?? 0,
    tts_total_ms: ttsEndTs && ttsStartTs ? ttsEndTs - ttsStartTs : 0,
    end_to_end_ms: now - turnStart
  });

  await sessionStore.update(session.sessionId, {
    history: session.history,
    level: session.level,
    context: session.context
  });
}
