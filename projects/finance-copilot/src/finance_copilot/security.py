"""Защита чувствительных данных.

Нефункциональное требование ТЗ: номера карт и другие банковские реквизиты
не сохраняются и не попадают в логи. Здесь два инструмента:

  * sanitize_description() — вычищает из текста номера карт/счетов и ФИО,
    вызывается ПАРСЕРОМ до того, как данные уйдут в БД или в LLM.
  * SensitiveDataFilter — logging.Filter, который дополнительно маскирует
    любые просочившиеся PAN-подобные последовательности в сообщениях логов.
"""

from __future__ import annotations

import logging
import re

# 13-19 цифр, возможно сгруппированных пробелами/дефисами — номера карт (PAN).
_PAN_RE = re.compile(r"\b(?:\d[ \-]?){13,19}\b")

# Маскированные хвосты карт вида *1234 / **** 1234 / xxxx1234
_CARD_TAIL_RE = re.compile(r"[*x•]{1,4}[ \-]?\d{4}\b", re.IGNORECASE)

# Номера счетов: 20 цифр подряд (российский формат счёта)
_ACCOUNT_RE = re.compile(r"\b\d{20}\b")

# Полные ФИО контрагента в назначении платежа:
#   "Перевод Иванову И. И." / "Возврат долга Петрову" и т.п.
# Убираем фамилию с инициалами, оставляя тип операции.
_FIO_INITIALS_RE = re.compile(
    r"\b[А-ЯЁ][а-яё]+(?:у|а|е|ой|ым|ому)?\s+[А-ЯЁ]\.\s*[А-ЯЁ]\.",
)


def sanitize_description(text: str) -> str:
    """Удаляет из описания операции чувствительные фрагменты.

    Возвращает безопасную для хранения/логов/LLM строку.
    """
    if not text:
        return ""
    cleaned = _ACCOUNT_RE.sub("[счёт]", text)
    cleaned = _PAN_RE.sub("[карта]", cleaned)
    cleaned = _CARD_TAIL_RE.sub("[карта]", cleaned)
    cleaned = _FIO_INITIALS_RE.sub("[контрагент]", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def mask_sensitive(text: str) -> str:
    """То же, что sanitize_description, но заточено под строки логов."""
    if not text:
        return text
    masked = _ACCOUNT_RE.sub("[счёт]", text)
    masked = _PAN_RE.sub("[карта]", masked)
    masked = _CARD_TAIL_RE.sub("[карта]", masked)
    return masked


class SensitiveDataFilter(logging.Filter):
    """Последний рубеж: маскирует PAN/счета в уже сформированных логах."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_sensitive(record.msg)
        if record.args:
            record.args = tuple(
                mask_sensitive(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def install_log_filter() -> None:
    """Навешивает SensitiveDataFilter на корневой логгер и его хендлеры."""
    root = logging.getLogger()
    f = SensitiveDataFilter()
    root.addFilter(f)
    for handler in root.handlers:
        handler.addFilter(f)
