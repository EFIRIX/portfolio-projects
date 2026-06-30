import { Pool } from 'pg';
import Redis from 'ioredis';
import { v4 as uuidv4 } from 'uuid';
import { SessionState } from '../types';
import { config } from '../config';

export interface SessionStore {
  create(personaId: string, subject: string): Promise<SessionState>;
  update(sessionId: string, partial: Partial<SessionState>): Promise<SessionState | undefined>;
  get(sessionId: string): Promise<SessionState | undefined>;
  health(): Promise<boolean>;
}

class InMemorySessionStore implements SessionStore {
  private sessions = new Map<string, SessionState>();
  async create(personaId: string, subject: string): Promise<SessionState> {
    const sessionId = uuidv4();
    const state: SessionState = { sessionId, personaId, subject, history: [], level: 'A0' };
    this.sessions.set(sessionId, state);
    return state;
  }
  async update(sessionId: string, partial: Partial<SessionState>): Promise<SessionState | undefined> {
    const current = this.sessions.get(sessionId);
    if (!current) return undefined;
    const updated = { ...current, ...partial } as SessionState;
    this.sessions.set(sessionId, updated);
    return updated;
  }
  async get(sessionId: string): Promise<SessionState | undefined> {
    return this.sessions.get(sessionId);
  }
  async health(): Promise<boolean> {
    return true;
  }
}

class RedisSessionStore implements SessionStore {
  constructor(private redis: Redis) {}
  async create(personaId: string, subject: string): Promise<SessionState> {
    const sessionId = uuidv4();
    const state: SessionState = { sessionId, personaId, subject, history: [], level: 'A0' };
    await this.redis.set(`session:${sessionId}`, JSON.stringify(state));
    return state;
  }
  async update(sessionId: string, partial: Partial<SessionState>): Promise<SessionState | undefined> {
    const existing = await this.get(sessionId);
    if (!existing) return undefined;
    const updated = { ...existing, ...partial } as SessionState;
    await this.redis.set(`session:${sessionId}`, JSON.stringify(updated));
    return updated;
  }
  async get(sessionId: string): Promise<SessionState | undefined> {
    const raw = await this.redis.get(`session:${sessionId}`);
    return raw ? (JSON.parse(raw) as SessionState) : undefined;
  }
  async health(): Promise<boolean> {
    try {
      await this.redis.ping();
      return true;
    } catch {
      return false;
    }
  }
}

class PostgresSessionStore implements SessionStore {
  constructor(private pool: Pool) {}
  async init() {
    await this.pool.query(`
      CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        persona_id TEXT,
        subject TEXT,
        history JSONB,
        level TEXT,
        context TEXT
      );
    `);
  }
  async create(personaId: string, subject: string): Promise<SessionState> {
    const sessionId = uuidv4();
    const state: SessionState = { sessionId, personaId, subject, history: [], level: 'A0' };
    await this.pool.query(
      'INSERT INTO sessions(session_id, persona_id, subject, history, level) VALUES($1,$2,$3,$4,$5)',
      [sessionId, personaId, subject, JSON.stringify(state.history), state.level]
    );
    return state;
  }
  async update(sessionId: string, partial: Partial<SessionState>): Promise<SessionState | undefined> {
    const existing = await this.get(sessionId);
    if (!existing) return undefined;
    const updated = { ...existing, ...partial } as SessionState;
    await this.pool.query(
      'UPDATE sessions SET persona_id=$1, subject=$2, history=$3, level=$4, context=$5 WHERE session_id=$6',
      [updated.personaId, updated.subject, JSON.stringify(updated.history), updated.level, updated.context ?? null, sessionId]
    );
    return updated;
  }
  async get(sessionId: string): Promise<SessionState | undefined> {
    const res = await this.pool.query('SELECT * FROM sessions WHERE session_id=$1 LIMIT 1', [sessionId]);
    if (res.rowCount === 0) return undefined;
    const row = res.rows[0];
    return {
      sessionId: row.session_id,
      personaId: row.persona_id,
      subject: row.subject,
      history: row.history ?? [],
      level: row.level ?? 'A0',
      context: row.context ?? undefined
    } as SessionState;
  }
  async health(): Promise<boolean> {
    try {
      await this.pool.query('SELECT 1');
      return true;
    } catch {
      return false;
    }
  }
}

export async function createSessionStore(): Promise<SessionStore> {
  if (config.redisUrl) {
    const redis = new Redis(config.redisUrl);
    return new RedisSessionStore(redis);
  }
  if (config.databaseUrl) {
    const pool = new Pool({ connectionString: config.databaseUrl });
    const store = new PostgresSessionStore(pool);
    await store.init();
    return store;
  }
  return new InMemorySessionStore();
}
