"""Тесты правил категоризации и ключевого критерия приёмки: >=80% без LLM."""

from datetime import date
from decimal import Decimal

import pytest

from finance_copilot.categorizer.rules_categorizer import RulesCategorizer
from finance_copilot.models import Transaction


@pytest.fixture
def categorizer() -> RulesCategorizer:
    # Используем реальные правила из config/category_rules.yaml.
    return RulesCategorizer()


def _tx(description: str, amount: str = "-100.00") -> Transaction:
    return Transaction(
        op_date=date(2026, 6, 20),
        amount=Decimal(amount),
        description=description,
    )


@pytest.mark.parametrize(
    "description,expected",
    [
        ("Пятёрочка", "еда"),
        ("Кофе с собой Coffee", "еда"),
        ("ВкусВилл", "еда"),
        ("Яндекс Такси", "транспорт"),
        ("АЗС Лукойл заправка", "транспорт"),
        ("Метрополитен Москва", "транспорт"),
        ("Аренда квартиры за июль", "жильё"),
        ("Оплата ЖКХ Мосэнергосбыт", "жильё"),
        ("STEAM GAMES", "развлечения"),
        ("Театр билеты", "развлечения"),
        ("Аптека Горздрав", "здоровье"),
        ("World Class фитнес", "здоровье"),
        ("NETFLIX.COM", "подписки"),
        ("Кинопоиск HD подписка", "подписки"),
    ],
)
def test_known_merchants_match(categorizer, description, expected):
    assert categorizer.match(description) == expected


def test_case_insensitive(categorizer):
    assert categorizer.match("пЯтЁрОчКа") == "еда"


def test_unknown_returns_none(categorizer):
    assert categorizer.match("Перевод Иванову И. И.") is None
    assert categorizer.match("OZON заказ 84213") is None
    assert categorizer.match("") is None


def test_categorize_marks_source_and_returns_remainder(categorizer):
    txs = [
        _tx("Пятёрочка"),
        _tx("Яндекс Такси"),
        _tx("Нечто неизвестное 123"),
    ]
    remainder = categorizer.categorize(txs)

    assert txs[0].category == "еда" and txs[0].source == "rules"
    assert txs[1].category == "транспорт"
    assert len(remainder) == 1
    assert remainder[0].description == "Нечто неизвестное 123"
    assert remainder[0].category is None


def test_priority_first_match_wins():
    # 'кафе' -> еда стоит раньше, чем 'бар' -> развлечения.
    rules = {
        "еда": ["кафе"],
        "развлечения": ["бар", "кафе"],
    }
    c = RulesCategorizer(rules=rules)
    assert c.match("Кафе-бар у дома") == "еда"


def test_at_least_80_percent_coverage_on_sample(categorizer):
    """Критерий приёмки: >=80% транзакций тестового файла — без LLM."""
    descriptions = [
        "Пятёрочка", "Яндекс Такси", "Аренда квартиры за июль",
        "Кинопоиск HD подписка", "Аптека Горздрав", "Магнит у дома",
        "АЗС Лукойл заправка", "NETFLIX.COM", "World Class фитнес",
        "Кофе с собой Coffee", "STEAM GAMES", "ВкусВилл",
        "Delivery Club заказ", "Метрополитен Москва",
        "Оплата ЖКХ Мосэнергосбыт", "Театр билеты",
        "Самокат доставка продуктов",
        # заведомо не распознаваемые правилами:
        "Перевод Иванову И. И.", "OZON заказ 84213", "Зарплата ООО Ромашка",
    ]
    txs = [_tx(d) for d in descriptions]
    remainder = categorizer.categorize(txs)
    matched = len(txs) - len(remainder)
    share = matched / len(txs)
    assert share >= 0.80, f"Покрытие правилами {share:.0%} < 80%"
