# Audio Streaming API (MVP)

Transport: WebSocket (`/api/stream/audio`), WebRTC planned later.

Providers (MVP): OpenAI Whisper streaming (STT), OpenAI gpt-4o-mini (LLM), OpenAI TTS (PCM 16k).

## Client → Server messages
- `start`: `{ "type": "start", "sessionId": "uuid", "personaId": "string", "sampleRate": 16000, "format": "pcm16|opus" }`
- `audio_chunk`: `{ "type": "audio_chunk", "data": "<base64 audio>", "timestamp": 1700000000000 }`
- `interrupt`: `{ "type": "interrupt" }` (barge-in)

## Server → Client messages
- `ack`: `{ "type": "ack", "timestamp": 1700000000000 }`
- `response_meta`: `{ "type": "response_meta", "turnId": "uuid", "text": "...", "emotion": "neutral|happy|serious", "level": "A0", "timestamp": 1700000000000 }`
- `tts_chunk`: `{ "type": "tts_chunk", "turnId": "uuid", "chunk": "<base64 pcm>", "timestamp": 1700000000000, "done": false }`
- `animation`: `{ "type": "animation", "turnId": "uuid", "payload": <animation-payload-json>, "timestamp": 1700000000000 }`
- `stopped`: `{ "type": "stopped", "turnId": "uuid" }` (after interrupt)
- `error`: `{ "type": "error", "message": "reason" }`

## Behavior
- Client sends `start` once per WebSocket, then streams `audio_chunk` packets (16 kHz PCM/Opus). 
- Server begins LLM + TTS as soon as first audio chunk arrives; `response_meta` is emitted before TTS completes; `tts_chunk` frames start before full text is ready.
- Barge-in: send `interrupt`; server stops current turn and awaits new `audio_chunk`.
- Audio chunks are batched server-side into ~320 ms windows with 1s backlog cap to control STT request fanout; schemas stay unchanged.

## Timing targets (p95)
- STT: ≤200 ms
- LLM: ≤250 ms
- TTS first chunk: ≤150 ms
- Network hop each way: ≤25 ms
- End-to-end: ≤700 ms

## Auth (placeholder)
- Header `Authorization: Bearer <token>` on WebSocket upgrade. Stubbed in MVP; add gateway later.
