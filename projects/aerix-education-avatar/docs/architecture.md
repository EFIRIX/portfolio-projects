# Architecture Snapshot (MVP)

## Services
- `api-gateway` (Fastify): HTTP + WebSocket for audio stream and session API.
- `ai-core` (in-process for MVP): orchestrates STT→LLM→TTS, attaches emotion + pedagogy metadata.
- `avatar-payload` (module): converts TTS + emotion tags into animation payload JSON.
- `session-store` (Redis by default when `REDIS_URL` set, fallback in-memory).

## Client
- Web/VR (Three.js + WebXR planned): renders classroom, captures mic 16 kHz, plays TTS stream with 50 ms jitter buffer, applies visemes within ±40 ms.

## Data flows
User mic → WebSocket `/api/stream/audio` → STT (OpenAI Whisper) → LLM (gpt-4o-mini) → TTS (OpenAI PCM stream) → animation payload → client avatar renderer.

## Swappable points
- STT adapter
- LLM provider
- TTS provider
- Animation retargeter (blendshape/rig mapping)

## Safety
- Content filter hook before TTS (stubbed)
- Moderation logs per turn
