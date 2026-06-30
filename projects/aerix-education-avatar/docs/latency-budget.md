# Latency Budget (p95 targets)

- STT: ≤200 ms
- LLM: ≤250 ms
- TTS first audio chunk: ≤150 ms
- Lip/animation pack: ≤50 ms
- Network each way: ≤25 ms
- Total user speech start → first TTS audio: ≤700 ms

Instrumentation
- Emit spans: `stt_ms`, `llm_first_token_ms`, `tts_first_chunk_ms`, `tts_total_ms`, `end_to_end_ms` per turn.
- Log fields: `sessionId`, `turnId`, `latency_ms`, `provider`, `status`, `timestamp`.
- `/health` returns rolling p95 for the above fields.
- Alert when any stage p95 > target for 5 consecutive mins.
