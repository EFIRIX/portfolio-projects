"""Доменные модели."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class Transaction:
    """Одна операция из выписки.

    Внимание: сюда НЕ попадают чувствительные банковские реквизиты
    (номер карты/счёта) — парсер их не переносит, см. csv_parser.py и security.py.
    """

    op_date: date
    amount: Decimal          # отрицательное = расход, положительное = доход
    description: str         # очищенное назначение платежа (без ФИО/карт)
    currency: str = "RUB"
    category: str | None = None
    # Как проставлена категория: "rules" | "llm" | "manual" | None
    source: str | None = None
    # Стабильный идентификатор для дедупликации/ручной правки
    tx_hash: str = ""

    @property
    def is_expense(self) -> bool:
        return self.amount < 0

    @property
    def abs_amount(self) -> Decimal:
        return abs(self.amount)


@dataclass
class CategorySummary:
    """Агрегат по одной категории за период."""

    category: str
    total: Decimal
    count: int


@dataclass
class WeeklyReport:
    """Данные для еженедельного отчёта со сравнением к прошлой неделе."""

    week_start: date
    week_end: date
    current: list[CategorySummary] = field(default_factory=list)
    previous: list[CategorySummary] = field(default_factory=list)
    total_current: Decimal = Decimal(0)
    total_previous: Decimal = Decimal(0)
    # Наблюдения от LLM, привязанные к конкретным цифрам
    insights: list[str] = field(default_factory=list)
    generated_at: datetime | None = None
