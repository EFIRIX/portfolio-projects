# AERIX Client (MVP)

- React + Vite + React Three Fiber placeholder scene.
- Connects to WebSocket `/api/stream/audio` and shows incoming events.
- Send `start` + mic audio to backend, display latency and avatar blendshape reaction.
- XR toggle via `VITE_XR_ENABLED` (default true).

Run (requires Node 18+):
```
npm install
npm run dev
```
