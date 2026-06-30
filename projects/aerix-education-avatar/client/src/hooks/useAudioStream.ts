import { useEffect, useMemo, useRef, useState } from 'react';
import { StreamClient, ClientEvent } from '../network/streamClient';
import { MicrophoneCapture } from '../audio/capture';
import { JitterPlayer } from '../audio/jitterPlayer';
import { VisemeScheduler, BlendshapeState } from '../audio/visemeScheduler';
import { AnimationPayload } from '../audio/types';

interface UseAudioStreamOptions {
  sessionId?: string;
  onBlendshapes?: (blend: BlendshapeState, emotion: string) => void;
}

export function useAudioStream(opts: UseAudioStreamOptions) {
  const { sessionId, onBlendshapes } = opts;
  const client = useMemo(() => new StreamClient(), []);
  const captureRef = useRef<MicrophoneCapture>();
  const playerRef = useRef<JitterPlayer>(new JitterPlayer());
  const visemeRef = useRef<VisemeScheduler>();

  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState<ClientEvent[]>([]);

  useEffect(() => {
    visemeRef.current = new VisemeScheduler(
      (blend, emotion) => onBlendshapes?.(blend, emotion),
      () => playerRef.current.getClock()
    );
  }, [onBlendshapes]);

  useEffect(() => {
    client.on((ev) => {
      if (ev.type === 'opened') {
        setConnected(true);
        playerRef.current.reset();
      }
      setEvents((prev) => [...prev, ev]);
      if (ev.type === 'tts_chunk' && ev.chunk) {
        playerRef.current.enqueue(ev.chunk).catch(console.error);
      }
      if (ev.type === 'animation' && ev.payload) {
        visemeRef.current?.schedule(ev.payload as AnimationPayload);
      }
      if (ev.type === 'error') {
        playerRef.current.reset();
      }
    });
    client.connect();
  }, [client]);

  const start = () => {
    if (!sessionId) return;
    client.start(sessionId, 16000);
  };

  const startMic = async () => {
    if (!sessionId) return;
    if (captureRef.current) return; // already started
    const capture = new MicrophoneCapture();
    captureRef.current = capture;
    await capture.start((chunk) => client.sendAudioChunk(chunk));
  };

  const stopMic = () => {
    captureRef.current?.stop();
    captureRef.current = undefined;
  };

  const interrupt = () => client.interrupt();

  return { connected, events, start, startMic, stopMic, interrupt };
}
