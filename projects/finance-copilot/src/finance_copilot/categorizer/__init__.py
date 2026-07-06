"""Категоризация транзакций.

Два независимых модуля с общим интерфейсом (base.Categorizer):
  * rules_categorizer.RulesCategorizer — детерминированный словарь ключевых слов.
  * llm_categorizer.LLMCategorizer      — fallback через LLMProvider, батчами.

pipeline.CategorizationPipeline связывает их в требуемом ТЗ порядке:
сначала правила, затем LLM только для нераспознанного остатка.
"""

from .base import Categorizer
from .pipeline import CategorizationPipeline
from .rules_categorizer import RulesCategorizer
from .llm_categorizer import LLMCategorizer

__all__ = [
    "Categorizer",
    "CategorizationPipeline",
    "RulesCategorizer",
    "LLMCategorizer",
]
