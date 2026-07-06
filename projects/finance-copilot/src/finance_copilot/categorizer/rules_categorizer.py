"""Категоризация по словарю ключевых слов (первый, основной этап).

Детерминированно, без сети и без LLM. Цель по ТЗ — покрывать >=80%
транзакций тестового файла, чтобы LLM звали как можно реже.
"""

from __future__ import annotations

import logging

from ..config import load_category_rules
from ..models import Transaction

logger = logging.getLogger(__name__)


class RulesCategorizer:
    """Проставляет категорию по вхождению ключевых слов из category_rules.yaml."""

    source_name = "rules"

    def __init__(self, rules: dict[str, list[str]] | None = None) -> None:
        # rules: {категория: [ключевые слова в нижнем регистре]}
        self.rules = rules if rules is not None else load_category_rules()

    def match(self, description: str) -> str | None:
        """Возвращает категорию для описания или None, если правил не нашлось."""
        text = (description or "").lower()
        if not text:
            return None
        for category, keywords in self.rules.items():
            for kw in keywords:
                if kw and kw in text:
                    return category
        return None

    def categorize(self, transactions: list[Transaction]) -> list[Transaction]:
        """Категоризирует что смог правилами, возвращает нераспознанный остаток."""
        unresolved: list[Transaction] = []
        for tx in transactions:
            category = self.match(tx.description)
            if category is not None:
                tx.category = category
                tx.source = self.source_name
            else:
                unresolved.append(tx)
        logger.info(
            "Правила: разобрано %d/%d, остаток для LLM: %d",
            len(transactions) - len(unresolved),
            len(transactions),
            len(unresolved),
        )
        return unresolved
