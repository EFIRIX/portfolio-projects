"""Общий интерфейс категоризаторов."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Transaction


class Categorizer(ABC):
    """Категоризатор проставляет .category и .source у транзакций.

    Контракт: метод categorize мутирует переданные транзакции (проставляет
    category/source там, где смог) и возвращает список тех, которые он НЕ смог
    категоризировать — чтобы следующий этап пайплайна занялся остатком.
    """

    #: строковый идентификатор источника, попадающий в Transaction.source
    source_name: str = "base"

    @abstractmethod
    def categorize(self, transactions: list[Transaction]) -> list[Transaction]:
        """Категоризирует что может, возвращает нераспознанный остаток."""
        raise NotImplementedError
