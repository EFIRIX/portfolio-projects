"""Инлайн-клавиатуры бота."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .. import CATEGORIES


def categories_keyboard(tx_id: int) -> InlineKeyboardMarkup:
    """Клавиатура выбора новой категории для транзакции tx_id."""
    buttons = [
        InlineKeyboardButton(text=cat, callback_data=f"setcat:{tx_id}:{cat}")
        for cat in CATEGORIES
    ]
    # по 2 кнопки в ряд
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recent_transactions_keyboard(rows: list[dict]) -> InlineKeyboardMarkup:
    """Список последних операций — выбрать, у какой править категорию."""
    kb = []
    for r in rows:
        amount = abs(float(r["amount"]))
        label = f"{r['op_date']} · {amount:.0f}₽ · {r['description'][:22]} [{r['category']}]"
        kb.append([InlineKeyboardButton(text=label, callback_data=f"pick:{r['id']}")])
    return InlineKeyboardMarkup(inline_keyboard=kb)
