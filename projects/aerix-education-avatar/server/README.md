# AERIX Server (MVP stub)

Fastify + WebSocket server for audio streaming, session API, and mock LLM/TTS/animation.

## Endpoints
- `GET /health`
- `POST /api/session` — create session
- `PATCH /api/session/:id` — update session
- `GET /api/session/:id` — resume session
- `WS /api/stream/audio` — bi-directional audio stream (see `../docs/api/streaming.md`)

## Run (requires Node 18+)
```
npm install
npm run dev
```
Env vars (see ../../.env.example):
- `OPENAI_API_KEY`, `OPENAI_MODEL` (default gpt-4o-mini)
- `TTS_MODEL` (default gpt-4o-mini-tts), `TTS_VOICE`
- `REDIS_URL` (enables Redis session store)

## Quick manual test
1) Start server
2) `curl -XPOST http://localhost:8787/api/session` → get `sessionId`
3) Open `client` dev server and click "Start Stream" then "Send Test Audio Chunk" to receive synthetic TTS + animation payloads.
