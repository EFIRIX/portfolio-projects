# Animation Payload (v1.0 JSON)

```json
{
  "version": "1.0",
  "phonemes": [{ "id": "AA", "start_ms": 120, "end_ms": 180 }],
  "visemes": [{ "id": "V3", "weight": 0.8 }],
  "blendshapes": { "mouthOpen": 0.6, "smile": 0.2 },
  "emotion": "neutral|happy|serious",
  "head": { "yaw": 0.1, "pitch": -0.05 },
  "eyes": { "blink": true, "gaze": [0, 0, 1] }
}
```

Client rules
- Apply visemes within ±40 ms of audio playback.
- Drive blendshapes at 30–60 FPS; interpolate missing frames.
- Idle layer must blend with speech layer without pops; disable idles when `phonemes` non-empty.
- Payload is versioned; clients must ignore unknown keys.
