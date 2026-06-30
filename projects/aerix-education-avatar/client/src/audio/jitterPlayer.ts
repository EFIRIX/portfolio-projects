const TARGET_BUFFER_MS = 50;
const SAMPLE_RATE = 16000;

export class JitterPlayer {
  private ctx: AudioContext;
  private lastScheduled = 0;

  constructor() {
    this.ctx = new AudioContext({ latencyHint: 'interactive', sampleRate: SAMPLE_RATE });
  }

  reset() {
    this.ctx.close();
    this.ctx = new AudioContext({ latencyHint: 'interactive', sampleRate: SAMPLE_RATE });
    this.lastScheduled = 0;
  }

  getClock() {
    return this.ctx.currentTime;
  }

  async enqueue(base64: string) {
    const data = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    const int16 = new Int16Array(data.buffer);
    const float32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 0x7fff;

    const buffer = this.ctx.createBuffer(1, float32.length, SAMPLE_RATE);
    buffer.copyToChannel(float32, 0);

    const duration = buffer.duration;
    let startTime = Math.max(this.ctx.currentTime + TARGET_BUFFER_MS / 1000, this.lastScheduled + 0.001);
    // gap concealment: if gap > 80ms insert silence
    if (startTime - this.lastScheduled > 0.08) {
      const silence = this.ctx.createBuffer(1, Math.floor(SAMPLE_RATE * 0.05), SAMPLE_RATE);
      const silentSource = this.ctx.createBufferSource();
      silentSource.buffer = silence;
      silentSource.connect(this.ctx.destination);
      silentSource.start(this.lastScheduled + 0.001);
      startTime = this.lastScheduled + 0.001 + silence.duration;
    }

    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.ctx.destination);
    src.start(startTime);
    this.lastScheduled = startTime + duration;
  }
}
