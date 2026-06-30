export type CaptureHandler = (chunk: ArrayBuffer) => void;

export class MicrophoneCapture {
  private ctx?: AudioContext;
  private processor?: ScriptProcessorNode;
  private stream?: MediaStream;
  private handler?: CaptureHandler;
  private targetRate = 16000;

  async start(onChunk: CaptureHandler) {
    this.handler = onChunk;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true
      }
    });
    this.ctx = new AudioContext({ latencyHint: 'interactive' });
    const source = this.ctx.createMediaStreamSource(this.stream);
    const bufferSize = 2048;
    this.processor = this.ctx.createScriptProcessor(bufferSize, 1, 1);
    source.connect(this.processor);
    this.processor.connect(this.ctx.destination);
    this.processor.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const resampled = this.downsample(input, this.ctx!.sampleRate, this.targetRate);
      const pcm = this.floatTo16BitPCM(resampled);
      this.handler?.(pcm.buffer);
    };
  }

  stop() {
    this.processor?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
  }

  private downsample(buffer: Float32Array, sampleRate: number, targetRate: number): Float32Array {
    if (targetRate === sampleRate) return buffer;
    const ratio = sampleRate / targetRate;
    const newLength = Math.floor(buffer.length / ratio);
    const result = new Float32Array(newLength);
    for (let i = 0; i < newLength; i++) {
      result[i] = buffer[Math.floor(i * ratio)];
    }
    return result;
  }

  private floatTo16BitPCM(buffer: Float32Array): Int16Array {
    const output = new Int16Array(buffer.length);
    for (let i = 0; i < buffer.length; i++) {
      const s = Math.max(-1, Math.min(1, buffer[i]));
      output[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    return output;
  }
}
