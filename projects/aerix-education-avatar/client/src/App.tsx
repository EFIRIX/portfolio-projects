import { useEffect, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, PerspectiveCamera } from '@react-three/drei';
import { XR, VRButton } from '@react-three/xr';
import { useAudioStream } from './hooks/useAudioStream';
import { BlendshapeState } from './audio/visemeScheduler';

const xrEnabled = import.meta.env.VITE_XR_ENABLED !== 'false';

function AvatarPreview({ blend, xr }: { blend: BlendshapeState; xr: boolean }) {
  const mouthOpen = blend.mouthOpen ?? 0.1;
  const smile = blend.smile ?? 0.1;
  return (
    <Canvas style={{ height: 360, background: '#0d1117' }}>
      {xr ? <XR /> : null}
      <ambientLight intensity={0.5} />
      <directionalLight position={[3, 5, 2]} intensity={0.8} />
      <mesh position={[0, 0, 0]}>
        <sphereGeometry args={[1, 32, 32]} />
        <meshStandardMaterial color="#5dade2" />
      </mesh>
      <mesh position={[0, -0.3, 1]} scale={[1, 1 + mouthOpen, 1]}>
        <boxGeometry args={[0.6, 0.2, 0.1]} />
        <meshStandardMaterial color="#f5b041" />
      </mesh>
      <mesh position={[0.35, 0.3, 1]} scale={[0.2, 0.2 + smile, 0.2]}>
        <boxGeometry args={[0.2, 0.05, 0.05]} />
        <meshStandardMaterial color="#fff" />
      </mesh>
      <mesh position={[-0.35, 0.3, 1]} scale={[0.2, 0.2 + smile, 0.2]}>
        <boxGeometry args={[0.2, 0.05, 0.05]} />
        <meshStandardMaterial color="#fff" />
      </mesh>
      {!xr && <OrbitControls enablePan={false} enableZoom={false} />}
      <PerspectiveCamera makeDefault position={[0, 0, 4]} />
    </Canvas>
  );
}

export default function App() {
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [blend, setBlend] = useState<BlendshapeState>({ mouthOpen: 0.1, smile: 0.1 });
  const [latency, setLatency] = useState<number | null>(null);
  const [xrMode, setXrMode] = useState(false);

  const stream = useAudioStream({
    sessionId,
    onBlendshapes: (b) => setBlend((prev) => ({ ...prev, ...b }))
  });

  useEffect(() => {
    fetch('/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) })
      .then((res) => res.json())
      .then((data) => setSessionId(data.session.sessionId))
      .catch(console.error);
  }, []);

  useEffect(() => {
    const turnStart: Record<string, number> = {};
    stream.events.forEach((ev) => {
      if (ev.type === 'response_meta') turnStart[ev.turnId] = performance.now();
      if (ev.type === 'tts_chunk' && ev.done && ev.turnId && turnStart[ev.turnId]) {
        setLatency(Math.round(performance.now() - turnStart[ev.turnId]));
      }
    });
  }, [stream.events]);

  return (
    <div style={{ fontFamily: 'Inter, system-ui, sans-serif', color: '#e5e7eb', background: '#111827', minHeight: '100vh' }}>
      <header style={{ padding: '16px 24px', borderBottom: '1px solid #1f2937' }}>
        <h1 style={{ margin: 0, fontSize: 20 }}>AERIX Real-Time Avatar MVP</h1>
        <div style={{ fontSize: 14, color: '#9ca3af' }}>Session: {sessionId ?? '…'} | Socket: {stream.connected ? 'connected' : 'connecting…'}</div>
      </header>

      <main style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, padding: 24 }}>
        <section style={{ background: '#0b1220', border: '1px solid #1f2937', borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Avatar Preview</h2>
          <AvatarPreview blend={blend} xr={xrMode && xrEnabled} />
        </section>

        <section style={{ background: '#0b1220', border: '1px solid #1f2937', borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Controls</h2>
          <button style={buttonStyle} onClick={stream.start} disabled={!sessionId}>Start Stream</button>
          <button style={buttonStyle} onClick={stream.startMic} disabled={!sessionId}>Start Mic</button>
          <button style={buttonStyle} onClick={stream.interrupt}>Interrupt</button>
          <button style={buttonStyle} onClick={stream.stopMic}>Stop Mic</button>
          <div style={{ marginTop: 12, color: '#9ca3af' }}>Measured turn latency: {latency ? `${latency} ms` : '—'}</div>
          {xrEnabled && (
            <div style={{ marginTop: 12 }}>
              <VRButton onClick={() => setXrMode(true)} />
            </div>
          )}
        </section>

        <section style={{ gridColumn: '1 / span 2', background: '#0b1220', border: '1px solid #1f2937', borderRadius: 12, padding: 16 }}>
          <h2 style={{ marginTop: 0 }}>Event Log</h2>
          <div style={{ maxHeight: 240, overflow: 'auto', fontFamily: 'ui-monospace', fontSize: 13 }}>
            {stream.events.slice(-20).map((ev, idx) => (
              <div key={idx}>
                {new Date().toLocaleTimeString()} — {JSON.stringify(ev)}
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

const buttonStyle: React.CSSProperties = {
  marginRight: 8,
  padding: '10px 14px',
  borderRadius: 8,
  border: '1px solid #2563eb',
  background: '#1d4ed8',
  color: '#e5e7eb',
  cursor: 'pointer'
};
