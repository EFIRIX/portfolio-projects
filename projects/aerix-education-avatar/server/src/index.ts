import Fastify from 'fastify';
import websocketPlugin from '@fastify/websocket';
import { Buffer } from 'buffer';
import { createSessionStore } from './persistence/sessionStore';
import { handleTurn } from './pipeline';
import { AudioStreamMessage, ServerMessage } from './types';
import { config } from './config';
import { getP95 } from './metrics';

async function main() {
  const sessionStore = await createSessionStore();
  const fastify = Fastify({ logger: true });
  fastify.register(websocketPlugin);

  fastify.get('/health', async () => {
    const redisHealthy = await sessionStore.health();
    const providers = {
      stt: Boolean(config.openaiApiKey || config.deepgramApiKey),
      llm: Boolean(config.openaiApiKey),
      tts: Boolean(config.openaiApiKey)
    };
    return { status: redisHealthy && providers.stt && providers.llm && providers.tts ? 'ok' : 'degraded', redis: redisHealthy, providers, latency_p95: getP95() };
  });

  fastify.post('/api/session', async (request, reply) => {
    const body = (request.body as any) ?? {};
    const personaId = body.personaId ?? 'default-persona';
    const subject = body.subject ?? 'math';
    const session = await sessionStore.create(personaId, subject);
    return { session };
  });

  fastify.patch('/api/session/:id', async (request, reply) => {
    const sessionId = (request.params as any).id;
    const body = (request.body as any) ?? {};
    const updated = await sessionStore.update(sessionId, body);
    if (!updated) return reply.code(404).send({ error: 'not_found' });
    return { session: updated };
  });

  fastify.get('/api/session/:id', async (request, reply) => {
    const sessionId = (request.params as any).id;
    const session = await sessionStore.get(sessionId);
    if (!session) return reply.code(404).send({ error: 'not_found' });
    return { session };
  });

  fastify.get('/api/stream/audio', { websocket: true }, (connection, req) => {
    let currentSessionId: string | undefined;
    let currentSampleRate = 16000;
    let abortController = new AbortController();
    let processing = false;
    const queue: Buffer[] = [];
    let queueBytes = 0;
    const minBytes = () => Math.floor(currentSampleRate * 2 * 0.32); // 320ms window
    const maxBytes = () => Math.floor(currentSampleRate * 2 * 1.0); // 1s cap

    const resetQueue = () => {
      queue.length = 0;
      queueBytes = 0;
    };

    const maybeProcess = async () => {
      if (processing) return;
      if (queueBytes < minBytes()) return;
      processing = true;
      const buffer = Buffer.concat(queue);
      resetQueue();
      abortController = new AbortController();
      try {
        const session = currentSessionId ? await sessionStore.get(currentSessionId) : undefined;
        if (!session) {
          connection.socket.send(JSON.stringify({ type: 'error', message: 'invalid sessionId' } satisfies ServerMessage));
        } else {
          await handleTurn({
            ws: connection,
            session,
            audioBuffer: buffer,
            sampleRate: currentSampleRate,
            abortFlag: { controller: abortController },
            sessionStore
          });
        }
      } catch (err) {
        connection.socket.send(JSON.stringify({ type: 'error', message: 'pipeline_failure' } satisfies ServerMessage));
        connection.socket.send(JSON.stringify({ type: 'stopped' } satisfies ServerMessage));
        console.error(err);
      } finally {
        processing = false;
        if (queueBytes >= minBytes()) void maybeProcess();
      }
    };

    connection.socket.on('message', async (raw: Buffer) => {
      try {
        const msg = JSON.parse(raw.toString()) as AudioStreamMessage;
        if (msg.type === 'start') {
          abortController = new AbortController();
          currentSessionId = msg.sessionId;
          currentSampleRate = msg.sampleRate ?? 16000;
          if (!currentSessionId) {
            connection.socket.send(JSON.stringify({ type: 'error', message: 'missing sessionId' } satisfies ServerMessage));
            return;
          }
          const session = await sessionStore.get(currentSessionId);
          if (!session) {
            connection.socket.send(JSON.stringify({ type: 'error', message: 'invalid sessionId' } satisfies ServerMessage));
            return;
          }
          connection.socket.send(JSON.stringify({ type: 'ack', timestamp: Date.now() } satisfies ServerMessage));
          return;
        }

        if (msg.type === 'interrupt') {
          abortController.abort();
          connection.socket.send(JSON.stringify({ type: 'stopped', turnId: undefined } satisfies ServerMessage));
          resetQueue();
          return;
        }

        if (msg.type === 'audio_chunk') {
          if (!currentSessionId) {
            connection.socket.send(JSON.stringify({ type: 'error', message: 'send start first' } satisfies ServerMessage));
            return;
          }
          const buffer = Buffer.from(msg.data ?? '', 'base64');
          queue.push(buffer);
          queueBytes += buffer.length;
          if (queueBytes > maxBytes()) {
            // drop oldest by shifting
            while (queueBytes > maxBytes() && queue.length > 0) {
              const dropped = queue.shift();
              if (dropped) queueBytes -= dropped.length;
            }
          }
          void maybeProcess();
          return;
        }
      } catch (err) {
        connection.socket.send(JSON.stringify({ type: 'error', message: 'bad_payload' } satisfies ServerMessage));
      }
    });

    connection.socket.on('close', () => {
      abortController.abort();
    });
  });

  await fastify.listen({ port: config.port, host: '0.0.0.0' });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
