"""Пайплайн категоризации: правила -> LLM fallback.

Это место, где ТЗ-требование «сначала правила, потом LLM только на остаток»
выражено явно в коде.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .. import DEFAULT_CATEGORY
from ..models import Transaction
from .llm_categorizer import LLMCategorizer
from .rules_categorizer import RulesCategorizer

logger = logging.getLogger(__name__)


@dataclass
class CategorizationStats:
    total: int
    by_rules: int
    by_llm: int
    by_default: int

    @property
    def rules_share(self) -> float:
        return self.by_rules / self.total if self.total else 0.0


class CategorizationPipeline:
    """Связывает RulesCategorizer и (опционально) LLMCategorizer."""

    def __init__(
        self,
        rules: RulesCategorizer | None = None,
        llm: LLMCategorizer | None = None,
    ) -> None:
        self.rules = rules or RulesCategorizer()
        self.llm = llm  # может быть None, если LLM отключён

    def run(self, transactions: list[Transaction]) -> CategorizationStats:
        """Категоризирует список транзакций на месте, возвращает статистику."""
        # Этап 1 — правила.
        remainder = self.rules.categorize(transactions)

        # Этап 2 — LLM только для остатка.
        if remainder and self.llm is not None:
            remainder = self.llm.categorize(remainder)

        # Этап 3 — всё, что не разобралось (LLM выключен/сбой) -> прочее.
        for tx in remainder:
            if tx.category is None:
                tx.category = DEFAULT_CATEGORY
                tx.source = "default"

        stats = CategorizationStats(
            total=len(transactions),
            by_rules=sum(1 for t in transactions if t.source == "rules"),
            by_llm=sum(1 for t in transactions if t.source == "llm"),
            by_default=sum(1 for t in transactions if t.source == "default"),
        )
        logger.info(
            "Категоризация завершена: правила=%.0f%%, llm=%d, дефолт=%d",
            stats.rules_share * 100,
            stats.by_llm,
            stats.by_default,
        )
        return stats
