export interface TurnMetrics {
  stt_ms: number;
  llm_first_token_ms: number;
  tts_first_chunk_ms: number;
  tts_total_ms: number;
  end_to_end_ms: number;
}

const window: TurnMetrics[] = [];
const MAX = 200;

export function recordMetrics(m: TurnMetrics) {
  window.push(m);
  if (window.length > MAX) window.shift();
}

function p95(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const idx = Math.floor(0.95 * (sorted.length - 1));
  return sorted[idx];
}

export function getP95() {
  return {
    stt_ms: p95(window.map((w) => w.stt_ms)),
    llm_first_token_ms: p95(window.map((w) => w.llm_first_token_ms)),
    tts_first_chunk_ms: p95(window.map((w) => w.tts_first_chunk_ms)),
    tts_total_ms: p95(window.map((w) => w.tts_total_ms)),
    end_to_end_ms: p95(window.map((w) => w.end_to_end_ms))
  };
}
