# Session API (MVP)

Base path: `/api/session`

## Create
- `POST /api/session`
- Body: `{ "personaId": "default-persona", "subject": "math" }`
- Response: `{ "session": { "sessionId": "uuid", "personaId": "...", "subject": "...", "history": [], "level": "A0" } }`

## Update
- `PATCH /api/session/:id`
- Body: partial session `{ history?: string[], level?: string, subject?: string }`
- Response: `{ "session": { ...updated } }`

## Resume
- `GET /api/session/:id`
- Response: `{ "session": { sessionId, personaId, subject, history, level } }`

Persistence: in-memory in MVP; swap for Redis/SQL later. Session state must restore persona, last context, and difficulty level.
