"""Хранилище истории транзакций в SQLite.

Важно (нефункциональное требование): в БД пишется только очищенное описание
операции. Номера карт/счетов и ФИО контрагентов сюда не попадают — они
вырезаются ещё в парсере (security.sanitize_description).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from .models import CategorySummary, Transaction

_SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    tx_hash     TEXT    NOT NULL,
    op_date     TEXT    NOT NULL,   -- ISO YYYY-MM-DD
    amount      TEXT    NOT NULL,   -- Decimal как строка, без потерь точности
    description TEXT    NOT NULL,   -- уже очищено от PAN/ФИО
    currency    TEXT    NOT NULL DEFAULT 'RUB',
    category    TEXT    NOT NULL,
    source      TEXT    NOT NULL,   -- rules | llm | manual | default
    UNIQUE(user_id, tx_hash)
);
CREATE INDEX IF NOT EXISTS idx_tx_user_date ON transactions(user_id, op_date);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def save_transactions(self, user_id: int, transactions: list[Transaction]) -> int:
        """Сохраняет транзакции, пропуская дубликаты (по user_id+tx_hash).

        Возвращает число фактически добавленных строк.
        """
        added = 0
        with self._connect() as conn:
            for tx in transactions:
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO transactions
                        (user_id, tx_hash, op_date, amount, description,
                         currency, category, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        tx.tx_hash,
                        tx.op_date.isoformat(),
                        str(tx.amount),
                        tx.description,
                        tx.currency,
                        tx.category or "прочее",
                        tx.source or "default",
                    ),
                )
                added += cur.rowcount
        return added

    def summary_between(
        self, user_id: int, start: date, end: date
    ) -> list[CategorySummary]:
        """Сумма расходов по категориям за [start, end] включительно.

        Учитываются только расходы (amount < 0); суммы возвращаются по модулю.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT category,
                       SUM(CAST(amount AS REAL)) AS total,
                       COUNT(*) AS cnt
                FROM transactions
                WHERE user_id = ?
                  AND op_date BETWEEN ? AND ?
                  AND CAST(amount AS REAL) < 0
                GROUP BY category
                ORDER BY total ASC
                """,
                (user_id, start.isoformat(), end.isoformat()),
            ).fetchall()
        return [
            CategorySummary(
                category=r["category"],
                total=Decimal(str(abs(r["total"]))).quantize(Decimal("0.01")),
                count=r["cnt"],
            )
            for r in rows
        ]

    def recent_transactions(self, user_id: int, limit: int = 20) -> list[dict]:
        """Последние операции пользователя (для команды ручной правки)."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, op_date, amount, description, category, source
                FROM transactions
                WHERE user_id = ?
                ORDER BY op_date DESC, id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_transaction(self, user_id: int, tx_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE user_id = ? AND id = ?",
                (user_id, tx_id),
            ).fetchone()
        return dict(row) if row else None

    def update_category(self, user_id: int, tx_id: int, category: str) -> bool:
        """Ручная правка категории. Проставляет source='manual'."""
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE transactions
                SET category = ?, source = 'manual'
                WHERE user_id = ? AND id = ?
                """,
                (category, user_id, tx_id),
            )
            return cur.rowcount > 0
