"""Тесты гибкого парсера CSV и защиты чувствительных данных.

Критерий приёмки: бот принимает CSV минимум двух банковских форматов без падения.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from finance_copilot.csv_parser import detect_format, parse_csv
from finance_copilot.security import sanitize_description

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _read(name: str) -> bytes:
    return (EXAMPLES / name).read_bytes()


def test_detect_tinkoff_format():
    name, _ = detect_format(_read("tinkoff_sample.csv"))
    assert name == "tinkoff"


def test_detect_sber_format():
    name, _ = detect_format(_read("sber_sample.csv"))
    assert name == "sber"


def test_parse_tinkoff_amounts_and_dates():
    txs = parse_csv(_read("tinkoff_sample.csv"))
    assert len(txs) == 20
    first = txs[0]
    assert first.amount == Decimal("-540.50")  # запятая как десятичный разделитель
    assert first.description == "Пятёрочка"
    assert first.currency == "RUB"


def test_parse_sber_two_formats_no_crash():
    txs = parse_csv(_read("sber_sample.csv"))
    assert len(txs) == 15
    assert any(t.amount == Decimal("-620.00") for t in txs)


def test_card_number_not_leaked_into_description():
    # Даже если PAN попал в описание — он вырезается.
    assert "1234" not in sanitize_description("Оплата картой 4276 3800 1234 5678")
    assert "[карта]" in sanitize_description("Оплата картой 4276 3800 1234 5678")


def test_fio_stripped():
    cleaned = sanitize_description("Перевод Иванову И. И.")
    assert "Иванов" not in cleaned
    assert "[контрагент]" in cleaned


def test_account_number_stripped():
    cleaned = sanitize_description("Зачисление на счёт 40817810099910004312")
    assert "40817810099910004312" not in cleaned


def test_tx_hash_is_stable():
    txs = parse_csv(_read("tinkoff_sample.csv"))
    again = parse_csv(_read("tinkoff_sample.csv"))
    assert txs[0].tx_hash == again[0].tx_hash
    assert txs[0].tx_hash != txs[1].tx_hash
