from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlparse


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    @classmethod
    def from_url(cls, database_url: str, project_root: Path) -> "Database":
        if database_url.startswith("sqlite:///"):
            raw = database_url.replace("sqlite:///", "", 1)
            path = Path(raw)
            if not path.is_absolute():
                path = project_root / path
            return cls(path)
        if database_url.startswith("sqlite:"):
            parsed = urlparse(database_url)
            return cls(Path(parsed.path))
        raise ValueError("Only sqlite:/// DATABASE_URL is supported in v1.")

    def initialize(self) -> None:
        with self._lock, self._conn:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    chat_id INTEGER,
                    user_id INTEGER,
                    message_id INTEGER,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    chat_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT,
                    text TEXT,
                    caption TEXT,
                    media_type TEXT,
                    file_id TEXT,
                    file_path TEXT,
                    raw_json TEXT,
                    created_at TEXT NOT NULL,
                    edited_at TEXT,
                    deleted_at TEXT,
                    PRIMARY KEY (chat_id, message_id)
                );

                CREATE TABLE IF NOT EXISTS settings (
                    scope TEXT NOT NULL,
                    chat_id INTEGER NOT NULL DEFAULT 0,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (scope, chat_id, user_id, key)
                );

                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    chat_id INTEGER,
                    message_id INTEGER,
                    user_id INTEGER,
                    media_type TEXT NOT NULL,
                    file_id TEXT,
                    file_unique_id TEXT,
                    path TEXT NOT NULL,
                    mime_type TEXT,
                    file_size INTEGER
                );

                CREATE TABLE IF NOT EXISTS business_connections (
                    connection_id TEXT PRIMARY KEY,
                    user_id INTEGER,
                    user_chat_id INTEGER,
                    is_enabled INTEGER NOT NULL,
                    can_reply INTEGER NOT NULL,
                    raw_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS archive_messages (
                    source_chat_id INTEGER NOT NULL,
                    source_message_id INTEGER NOT NULL,
                    source_user_id INTEGER,
                    username TEXT,
                    display_name TEXT,
                    media_type TEXT,
                    archive_chat_id INTEGER NOT NULL,
                    archive_thread_id INTEGER,
                    archive_message_id INTEGER NOT NULL,
                    archive_mode TEXT NOT NULL DEFAULT 'channel',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source_chat_id, source_message_id)
                );

                CREATE TABLE IF NOT EXISTS archive_threads (
                    source_chat_id INTEGER NOT NULL,
                    source_user_id INTEGER NOT NULL DEFAULT 0,
                    title TEXT NOT NULL,
                    archive_group_id INTEGER NOT NULL,
                    message_thread_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source_chat_id, source_user_id, archive_group_id)
                );

                CREATE TABLE IF NOT EXISTS mtproxy_candidates (
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    secret TEXT NOT NULL,
                    source TEXT NOT NULL,
                    raw_url TEXT,
                    last_seen_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    last_ok_at TEXT,
                    latency_ms INTEGER,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (host, port, secret)
                );

                CREATE TABLE IF NOT EXISTS socks_proxy_candidates (
                    scheme TEXT NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    password TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL,
                    raw_url TEXT,
                    last_seen_at TEXT NOT NULL,
                    last_checked_at TEXT,
                    last_ok_at TEXT,
                    latency_ms INTEGER,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (scheme, host, port, username, password)
                );
                """
            )
            self._ensure_column("archive_messages", "archive_thread_id", "INTEGER")
            self._ensure_column("archive_messages", "archive_mode", "TEXT NOT NULL DEFAULT 'channel'")

    def log_event(
        self,
        level: str,
        event_type: str,
        chat_id: Optional[int],
        user_id: Optional[int],
        message_id: Optional[int],
        payload: Dict[str, Any],
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO events (created_at, level, event_type, chat_id, user_id, message_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (utc_now(), level, event_type, chat_id, user_id, message_id, json.dumps(payload, ensure_ascii=False)),
            )

    def last_events(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def count(self, table: str) -> int:
        if table not in {
            "events",
            "messages",
            "settings",
            "media",
            "business_connections",
            "archive_messages",
            "archive_threads",
            "mtproxy_candidates",
            "socks_proxy_candidates",
        }:
            raise ValueError("Unknown table")
        with self._lock:
            row = self._conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
        return int(row["count"])

    def upsert_message(self, message: Dict[str, Any]) -> None:
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO messages (
                    chat_id, message_id, user_id, username, text, caption, media_type,
                    file_id, file_path, raw_json, created_at, edited_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, message_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    username=excluded.username,
                    text=excluded.text,
                    caption=excluded.caption,
                    media_type=excluded.media_type,
                    file_id=excluded.file_id,
                    file_path=excluded.file_path,
                    raw_json=excluded.raw_json,
                    edited_at=excluded.edited_at
                """,
                (
                    message["chat_id"],
                    message["message_id"],
                    message.get("user_id"),
                    message.get("username"),
                    message.get("text"),
                    message.get("caption"),
                    message.get("media_type"),
                    message.get("file_id"),
                    message.get("file_path"),
                    message.get("raw_json"),
                    message.get("created_at", now),
                    message.get("edited_at"),
                    message.get("deleted_at"),
                ),
            )

    def mark_deleted(self, chat_id: int, message_ids: Iterable[int]) -> None:
        with self._lock, self._conn:
            self._conn.executemany(
                "UPDATE messages SET deleted_at=? WHERE chat_id=? AND message_id=?",
                [(utc_now(), chat_id, message_id) for message_id in message_ids],
            )

    def get_message(self, chat_id: int, message_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def known_chats(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT chat_id, COUNT(*) AS messages, MAX(created_at) AS last_seen
                FROM messages
                GROUP BY chat_id
                ORDER BY last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def cached_messages_for_archive(self, limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT m.*
                FROM messages m
                LEFT JOIN archive_messages a
                    ON a.source_chat_id=m.chat_id AND a.source_message_id=m.message_id
                WHERE a.source_message_id IS NULL
                ORDER BY m.created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def latest_peer_for_chat(self, chat_id: int, owner_ids: Sequence[int]) -> Optional[Dict[str, Any]]:
        owner_ids = [int(owner_id) for owner_id in owner_ids if owner_id is not None]
        params: List[Any] = [int(chat_id)]
        owner_filter = ""
        if owner_ids:
            placeholders = ", ".join("?" for _ in owner_ids)
            owner_filter = f"AND (user_id IS NULL OR user_id NOT IN ({placeholders}))"
            params.extend(owner_ids)
        with self._lock:
            row = self._conn.execute(
                f"""
                SELECT user_id, username, chat_id, MAX(created_at) AS last_seen
                FROM messages
                WHERE chat_id=?
                {owner_filter}
                GROUP BY user_id, username, chat_id
                ORDER BY last_seen DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def set_setting(self, scope: str, key: str, value: str, chat_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
        stored_chat_id = int(chat_id or 0)
        stored_user_id = int(user_id or 0)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO settings (scope, chat_id, user_id, key, value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, chat_id, user_id, key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (scope, stored_chat_id, stored_user_id, key, value, utc_now()),
            )

    def get_setting(self, scope: str, key: str, chat_id: Optional[int] = None, user_id: Optional[int] = None, default: str = "") -> str:
        stored_chat_id = int(chat_id or 0)
        stored_user_id = int(user_id or 0)
        with self._lock:
            row = self._conn.execute(
                """
                SELECT value FROM settings
                WHERE scope=? AND key=? AND chat_id=? AND user_id=?
                """,
                (scope, key, stored_chat_id, stored_user_id),
            ).fetchone()
        return str(row["value"]) if row else default

    def settings(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM settings ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def add_media(self, item: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO media (
                    created_at, chat_id, message_id, user_id, media_type, file_id,
                    file_unique_id, path, mime_type, file_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now(),
                    item.get("chat_id"),
                    item.get("message_id"),
                    item.get("user_id"),
                    item["media_type"],
                    item.get("file_id"),
                    item.get("file_unique_id"),
                    item["path"],
                    item.get("mime_type"),
                    item.get("file_size"),
                ),
            )

    def last_media(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM media ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def upsert_business_connection(self, connection: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO business_connections (
                    connection_id, user_id, user_chat_id, is_enabled, can_reply, raw_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(connection_id) DO UPDATE SET
                    user_id=excluded.user_id,
                    user_chat_id=excluded.user_chat_id,
                    is_enabled=excluded.is_enabled,
                    can_reply=excluded.can_reply,
                    raw_json=excluded.raw_json,
                    updated_at=excluded.updated_at
                """,
                (
                    connection["connection_id"],
                    connection.get("user_id"),
                    connection.get("user_chat_id"),
                    1 if connection.get("is_enabled") else 0,
                    1 if connection.get("can_reply") else 0,
                    json.dumps(connection.get("raw", {}), ensure_ascii=False),
                    utc_now(),
                ),
            )

    def last_business_connections(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM business_connections ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def business_summary(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_enabled=1 THEN 1 ELSE 0 END) AS enabled,
                    SUM(CASE WHEN can_reply=1 THEN 1 ELSE 0 END) AS can_reply,
                    MAX(updated_at) AS updated_at
                FROM business_connections
                """
            ).fetchone()
        total = int(row["total"] or 0)
        enabled = int(row["enabled"] or 0)
        can_reply = int(row["can_reply"] or 0)
        return {
            "total": total,
            "enabled": enabled > 0,
            "can_reply": can_reply > 0,
            "updated_at": row["updated_at"],
        }

    def save_archive_mapping(self, item: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO archive_messages (
                    source_chat_id, source_message_id, source_user_id, username,
                    display_name, media_type, archive_chat_id, archive_thread_id,
                    archive_message_id, archive_mode, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_chat_id, source_message_id) DO UPDATE SET
                    source_user_id=excluded.source_user_id,
                    username=excluded.username,
                    display_name=excluded.display_name,
                    media_type=excluded.media_type,
                    archive_chat_id=excluded.archive_chat_id,
                    archive_thread_id=excluded.archive_thread_id,
                    archive_message_id=excluded.archive_message_id,
                    archive_mode=excluded.archive_mode,
                    created_at=excluded.created_at
                """,
                (
                    item["source_chat_id"],
                    item["source_message_id"],
                    item.get("source_user_id"),
                    item.get("username"),
                    item.get("display_name"),
                    item.get("media_type"),
                    item["archive_chat_id"],
                    item.get("archive_thread_id"),
                    item["archive_message_id"],
                    item.get("archive_mode", "channel"),
                    item.get("created_at", utc_now()),
                ),
            )

    def get_archive_mapping(self, source_chat_id: int, source_message_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM archive_messages WHERE source_chat_id=? AND source_message_id=?",
                (source_chat_id, source_message_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def archive_summary(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    MAX(created_at) AS last_created_at,
                    MAX(archive_chat_id) AS archive_chat_id,
                    SUM(CASE WHEN archive_mode='forum' THEN 1 ELSE 0 END) AS forum_total
                FROM archive_messages
                """
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "forum_total": int(row["forum_total"] or 0),
            "last_created_at": row["last_created_at"],
            "archive_chat_id": row["archive_chat_id"],
        }

    def save_archive_thread(self, item: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO archive_threads (
                    source_chat_id, source_user_id, title, archive_group_id,
                    message_thread_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_chat_id, source_user_id, archive_group_id) DO UPDATE SET
                    title=excluded.title,
                    message_thread_id=excluded.message_thread_id,
                    created_at=excluded.created_at
                """,
                (
                    item["source_chat_id"],
                    int(item.get("source_user_id") or 0),
                    item["title"],
                    item["archive_group_id"],
                    item["message_thread_id"],
                    item.get("created_at", utc_now()),
                ),
            )

    def get_archive_thread(self, source_chat_id: int, source_user_id: Optional[int], archive_group_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM archive_threads
                WHERE source_chat_id=? AND source_user_id=? AND archive_group_id=?
                """,
                (source_chat_id, int(source_user_id or 0), archive_group_id),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def archive_thread_summary(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COUNT(*) AS total, MAX(created_at) AS last_created_at, MAX(archive_group_id) AS archive_group_id
                FROM archive_threads
                """
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "last_created_at": row["last_created_at"],
            "archive_group_id": row["archive_group_id"],
        }

    def upsert_mtproxy_candidate(self, item: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO mtproxy_candidates (
                    host, port, secret, source, raw_url, last_seen_at,
                    last_checked_at, last_ok_at, latency_ms, fail_count, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, port, secret) DO UPDATE SET
                    source=excluded.source,
                    raw_url=excluded.raw_url,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    item["host"],
                    int(item["port"]),
                    item["secret"],
                    item.get("source", "unknown"),
                    item.get("raw_url"),
                    item.get("last_seen_at", utc_now()),
                    item.get("last_checked_at"),
                    item.get("last_ok_at"),
                    item.get("latency_ms"),
                    int(item.get("fail_count", 0)),
                    1 if item.get("is_active") else 0,
                ),
            )

    def mtproxy_candidates(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM mtproxy_candidates
                ORDER BY
                    is_active DESC,
                    (last_ok_at IS NULL) ASC,
                    last_ok_at DESC,
                    fail_count ASC,
                    (latency_ms IS NULL) ASC,
                    latency_ms ASC,
                    last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_mtproxy_check(self, host: str, port: int, secret: str, ok: bool, latency_ms: Optional[int], error: str = "") -> None:
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE mtproxy_candidates
                SET
                    last_checked_at=?,
                    last_ok_at=CASE WHEN ? THEN ? ELSE last_ok_at END,
                    latency_ms=CASE WHEN ? THEN ? ELSE latency_ms END,
                    fail_count=CASE WHEN ? THEN 0 ELSE fail_count + 1 END,
                    is_active=?
                WHERE host=? AND port=? AND secret=?
                """,
                (
                    now,
                    1 if ok else 0,
                    now,
                    1 if ok else 0,
                    latency_ms,
                    1 if ok else 0,
                    1 if ok else 0,
                    host,
                    int(port),
                    secret,
                ),
            )
        if error:
            self.set_setting("global", "mtproxy:last_error", error)

    def mtproxy_summary(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) AS active,
                    MAX(last_seen_at) AS last_seen_at,
                    MAX(last_ok_at) AS last_ok_at,
                    MIN(CASE WHEN is_active=1 THEN latency_ms ELSE NULL END) AS best_latency_ms
                FROM mtproxy_candidates
                """
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
            "last_seen_at": row["last_seen_at"],
            "last_ok_at": row["last_ok_at"],
            "best_latency_ms": row["best_latency_ms"],
        }

    def upsert_socks_proxy_candidate(self, item: Dict[str, Any]) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO socks_proxy_candidates (
                    scheme, host, port, username, password, source, raw_url, last_seen_at,
                    last_checked_at, last_ok_at, latency_ms, fail_count, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scheme, host, port, username, password) DO UPDATE SET
                    source=excluded.source,
                    raw_url=excluded.raw_url,
                    last_seen_at=excluded.last_seen_at
                """,
                (
                    item["scheme"],
                    item["host"],
                    int(item["port"]),
                    item.get("username") or "",
                    item.get("password") or "",
                    item.get("source", "unknown"),
                    item.get("raw_url"),
                    item.get("last_seen_at", utc_now()),
                    item.get("last_checked_at"),
                    item.get("last_ok_at"),
                    item.get("latency_ms"),
                    int(item.get("fail_count", 0)),
                    1 if item.get("is_active") else 0,
                ),
            )

    def socks_proxy_candidates(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT *
                FROM socks_proxy_candidates
                ORDER BY
                    is_active DESC,
                    (last_ok_at IS NULL) ASC,
                    last_ok_at DESC,
                    fail_count ASC,
                    (latency_ms IS NULL) ASC,
                    latency_ms ASC,
                    last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_socks_proxy_check(
        self,
        scheme: str,
        host: str,
        port: int,
        username: Optional[str],
        password: Optional[str],
        ok: bool,
        latency_ms: Optional[int],
        error: str = "",
    ) -> None:
        now = utc_now()
        with self._lock, self._conn:
            self._conn.execute(
                """
                UPDATE socks_proxy_candidates
                SET
                    last_checked_at=?,
                    last_ok_at=CASE WHEN ? THEN ? ELSE last_ok_at END,
                    latency_ms=CASE WHEN ? THEN ? ELSE latency_ms END,
                    fail_count=CASE WHEN ? THEN 0 ELSE fail_count + 1 END,
                    is_active=?
                WHERE scheme=? AND host=? AND port=? AND username=? AND password=?
                """,
                (
                    now,
                    1 if ok else 0,
                    now,
                    1 if ok else 0,
                    latency_ms,
                    1 if ok else 0,
                    1 if ok else 0,
                    scheme,
                    host,
                    int(port),
                    username or "",
                    password or "",
                ),
            )
        if error:
            self.set_setting("global", "socks:last_error", error)

    def socks_proxy_summary(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN is_active=1 THEN 1 ELSE 0 END) AS active,
                    MAX(last_seen_at) AS last_seen_at,
                    MAX(last_ok_at) AS last_ok_at,
                    MIN(CASE WHEN is_active=1 THEN latency_ms ELSE NULL END) AS best_latency_ms
                FROM socks_proxy_candidates
                """
            ).fetchone()
        return {
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
            "last_seen_at": row["last_seen_at"],
            "last_ok_at": row["last_ok_at"],
            "best_latency_ms": row["best_latency_ms"],
        }

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        columns = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        result = dict(row)
        if "payload" in result:
            with suppress_json_error():
                result["payload"] = json.loads(result["payload"])
        return result


class suppress_json_error:
    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        return exc_type in {json.JSONDecodeError, TypeError}
