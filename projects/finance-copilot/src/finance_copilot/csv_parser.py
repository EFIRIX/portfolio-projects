"""Гибкий парсер банковских CSV-выписок.

Форматы колонок не зашиты в код — они описаны в config/bank_formats.yaml.
Парсер автоматически подбирает формат, у которого все обязательные колонки
присутствуют в заголовке файла. Добавление нового банка = правка YAML.
"""

from __future__ import annotations

import hashlib
import io
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

from .config import load_bank_formats
from .models import Transaction
from .security import sanitize_description

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ("date", "amount", "description")


class CSVParseError(Exception):
    """Не удалось распознать формат или разобрать файл."""


def _read_header(raw: bytes, encoding: str, delimiter: str) -> list[str]:
    text = raw.decode(encoding, errors="replace")
    first_line = text.splitlines()[0] if text.splitlines() else ""
    return [c.strip().strip('"') for c in first_line.split(delimiter)]


def detect_format(raw: bytes, formats: dict[str, dict] | None = None) -> tuple[str, dict]:
    """Возвращает (имя_формата, описание_формата) для данного файла.

    Берёт первый формат из bank_formats.yaml, все обязательные колонки
    которого найдены в заголовке. Порядок в YAML задаёт приоритет.
    """
    formats = formats if formats is not None else load_bank_formats()
    for name, spec in formats.items():
        delimiter = spec.get("delimiter", ",")
        encoding = spec.get("encoding", "utf-8")
        try:
            header = _read_header(raw, encoding, delimiter)
        except (UnicodeError, IndexError):
            continue
        needed = [spec["columns"][f] for f in REQUIRED_FIELDS]
        if all(col in header for col in needed):
            return name, spec
    raise CSVParseError(
        "Не удалось определить формат выписки. "
        "Проверьте, что колонки описаны в config/bank_formats.yaml."
    )


def _parse_amount(value, decimal_sep: str, thousands_sep: str) -> Decimal | None:
    if value is None:
        return None
    s = str(value).strip().replace("\xa0", " ")
    if not s:
        return None
    # Убираем разделитель тысяч, приводим десятичный разделитель к точке.
    if thousands_sep:
        s = s.replace(thousands_sep, "")
    s = s.replace(" ", "")
    if decimal_sep and decimal_sep != ".":
        s = s.replace(decimal_sep, ".")
    s = s.replace("+", "")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value, date_format: str):
    s = str(value).strip()
    # Пробуем заявленный формат, затем несколько распространённых.
    candidates = [date_format, "%d.%m.%Y %H:%M:%S", "%d.%m.%Y", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"]
    for fmt in candidates:
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    # Последняя попытка — pandas.
    try:
        return pd.to_datetime(s, dayfirst=True).date()
    except Exception:  # noqa: BLE001 - широкий catch: битая дата пропускается
        return None


def _make_hash(op_date, amount: Decimal, description: str) -> str:
    key = f"{op_date.isoformat()}|{amount}|{description}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def parse_csv(raw: bytes, formats: dict[str, dict] | None = None) -> list[Transaction]:
    """Разбирает CSV в список Transaction.

    Чувствительные поля (карта/счёт/ФИО) вычищаются из описания сразу,
    остальные колонки исходника (номер карты и т.п.) в модель не переносятся.
    """
    format_name, spec = detect_format(raw, formats)
    logger.info("Определён формат выписки: %s", format_name)

    cols = spec["columns"]
    delimiter = spec.get("delimiter", ",")
    encoding = spec.get("encoding", "utf-8")
    decimal_sep = spec.get("decimal", ".")
    thousands_sep = spec.get("thousands", "")
    date_format = spec.get("date_format", "%Y-%m-%d")

    df = pd.read_csv(
        io.BytesIO(raw),
        sep=delimiter,
        encoding=encoding,
        dtype=str,
        keep_default_na=False,
    )
    df.columns = [c.strip() for c in df.columns]

    transactions: list[Transaction] = []
    skipped = 0
    for _, row in df.iterrows():
        amount = _parse_amount(row.get(cols["amount"]), decimal_sep, thousands_sep)
        op_date = _parse_date(row.get(cols["date"]), date_format)
        raw_desc = row.get(cols["description"], "")
        if amount is None or op_date is None:
            skipped += 1
            continue
        description = sanitize_description(str(raw_desc))
        currency_col = cols.get("currency")
        currency = str(row.get(currency_col, "RUB")).strip() if currency_col else "RUB"
        currency = currency or "RUB"

        transactions.append(
            Transaction(
                op_date=op_date,
                amount=amount,
                description=description,
                currency=currency,
                tx_hash=_make_hash(op_date, amount, description),
            )
        )

    if skipped:
        logger.warning("Пропущено строк при разборе: %d", skipped)
    if not transactions:
        raise CSVParseError("В файле не найдено ни одной корректной операции.")
    return transactions
