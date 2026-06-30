# AI Real-Time Avatar Education MVP

This repo contains a minimal scaffold for the MVP described in FINAL SPEC:
- `server/` Fastify WebSocket server with session API, mock STT→LLM→TTS pipeline, animation payloads, and barge-in.
- `client/` React + Three.js preview that connects to the stream, sends test audio chunks, and visualizes blendshapes.
- `docs/` API and payload specs, latency budget, architecture snapshot.

## Quickstart (after installing Node 18+)
1) Server: `cd server && npm install && npm run dev`
2) Client: `cd client && npm install && npm run dev`
3) Open http://localhost:5173, click *Start Stream* then *Send Test Audio Chunk* to see synthetic TTS + animation.

Set environment via `.env` (see `.env.example`) for OpenAI keys and Redis.

## Key Interfaces
- Audio stream protocol: `docs/api/streaming.md`
- Animation payload: `docs/animation-payload.md`
- Session API: `docs/api/session.md`
- Latency targets: `docs/latency-budget.md`

## Next Implementation Steps
- Swap mock STT/LLM/TTS with providers (e.g., Whisper / GPT-4 / Neural TTS) but keep the same message schema.
- Add real mic capture + Opus/PCM encoder on client; implement jitter buffer and lip-sync timing.
- Replace in-memory session store with Redis/Postgres, add auth on WebSocket upgrade.
- Implement content filter provider before TTS and log moderation events.
- Add WebXR controls for mobile VR and retarget animation payload to rig-specific blendshape names.
