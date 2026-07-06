"""LLM-fallback категоризация (второй этап).

Вызывается ТОЛЬКО для транзакций, которые не разобрал RulesCategorizer.
Запросы к модели идут батчами по LLM_BATCH_SIZE (20-30) транзакций, чтобы
не делать по запросу на каждую строку.
"""

from __future__ import annotations

import json
import logging

from .. import CATEGORIES, DEFAULT_CATEGORY
from ..llm.base import LLMProvider
from ..models import Transaction

logger = logging.getLogger(__name__)

_ALLOWED = set(CATEGORIES)

_SYSTEM_PROMPT = (
    "Ты классификатор банковских операций. Отнеси каждую операцию к одной из "
    "категорий: " + ", ".join(CATEGORIES) + ". "
    "Отвечай строго JSON-массивом объектов вида {\"i\": <номер>, \"category\": "
    "\"<категория>\"} без пояснений. Если не уверен — используй \"прочее\"."
)


class LLMCategorizer:
    """Категоризация нераспознанного остатка через LLMProvider батчами."""

    source_name = "llm"

    def __init__(self, provider: LLMProvider, batch_size: int = 25) -> None:
        self.provider = provider
        self.batch_size = max(1, batch_size)

    def categorize(self, transactions: list[Transaction]) -> list[Transaction]:
        """Проставляет категории. Возвращает то, что осталось без категории.

        При ошибке/недоступности LLM оставшиеся транзакции получают
        DEFAULT_CATEGORY, чтобы пользователь всё равно получил результат.
        """
        unresolved: list[Transaction] = []
        for start in range(0, len(transactions), self.batch_size):
            batch = transactions[start : start + self.batch_size]
            try:
                self._categorize_batch(batch)
            except Exception as exc:  # noqa: BLE001 - деградируем мягко
                logger.warning("LLM-категоризация не удалась: %s", exc)
                for tx in batch:
                    tx.category = DEFAULT_CATEGORY
                    tx.source = self.source_name
            unresolved.extend(tx for tx in batch if tx.category is None)
        return unresolved

    def _build_prompt(self, batch: list[Transaction]) -> str:
        lines = [
            f"{i}. {tx.description or '(без описания)'}"
            for i, tx in enumerate(batch)
        ]
        return (
            "Классифицируй операции ниже. Верни JSON-массив.\n\n"
            + "\n".join(lines)
        )

    def _categorize_batch(self, batch: list[Transaction]) -> None:
        prompt = self._build_prompt(batch)
        raw = self.provider.complete(prompt, system=_SYSTEM_PROMPT)
        mapping = self._parse_response(raw)
        for i, tx in enumerate(batch):
            category = mapping.get(i)
            if category in _ALLOWED:
                tx.category = category
                tx.source = self.source_name

    @staticmethod
    def _parse_response(raw: str) -> dict[int, str]:
        """Извлекает {индекс: категория} из ответа модели, устойчиво к мусору."""
        text = (raw or "").strip()
        # Модель иногда оборачивает JSON в ```; вырезаем содержимое массива.
        first, last = text.find("["), text.rfind("]")
        if first != -1 and last != -1 and last > first:
            text = text[first : last + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Не удалось распарсить ответ LLM как JSON")
            return {}
        result: dict[int, str] = {}
        for item in data if isinstance(data, list) else []:
            try:
                result[int(item["i"])] = str(item["category"]).strip().lower()
            except (KeyError, ValueError, TypeError):
                continue
        return result
