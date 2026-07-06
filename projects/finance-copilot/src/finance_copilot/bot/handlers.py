"""Хендлеры бота: загрузка CSV, отчёт, ручная правка категории."""

from __future__ import annotations

import asyncio
import io
import logging
from collections import Counter
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from .. import CATEGORIES
from ..categorizer import CategorizationPipeline, LLMCategorizer, RulesCategorizer
from ..config import Settings
from ..csv_parser import CSVParseError, parse_csv
from ..db import Database
from ..llm.base import LLMProvider
from ..report import build_report, format_report
from .keyboards import categories_keyboard, recent_transactions_keyboard

logger = logging.getLogger(__name__)
router = Router()

_HELP = (
    "👋 Я *Финансовый копайлот*.\n\n"
    "Пришлите CSV-выписку из банка (Тинькофф/Сбер и др.) — я разложу траты "
    "по категориям и найду закономерности.\n\n"
    "*Команды:*\n"
    "/report — отчёт за неделю со сравнением к прошлой\n"
    "/fix — вручную поправить категорию операции\n"
    "/help — эта справка\n\n"
    "🔒 Я не сохраняю номера карт, счетов и ФИО — они вырезаются при загрузке."
)


def _build_pipeline(settings: Settings, provider: LLMProvider | None) -> CategorizationPipeline:
    """Собирает пайплайн: правила + (если есть провайдер) LLM-fallback."""
    llm = LLMCategorizer(provider, settings.llm_batch_size) if provider else None
    return CategorizationPipeline(rules=RulesCategorizer(), llm=llm)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(_HELP, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(_HELP, parse_mode="Markdown")


@router.message(F.document)
async def handle_document(
    message: Message,
    db: Database,
    settings: Settings,
    provider: LLMProvider | None,
) -> None:
    """Приём CSV: парсинг → категоризация (правила→LLM) → сохранение → сводка."""
    doc = message.document
    if not doc.file_name.lower().endswith(".csv"):
        await message.answer("Пришлите файл в формате *.csv*.", parse_mode="Markdown")
        return

    buffer = io.BytesIO()
    await message.bot.download(doc, destination=buffer)
    raw = buffer.getvalue()

    status = await message.answer("⏳ Разбираю выписку…")
    try:
        transactions = parse_csv(raw)
    except CSVParseError as exc:
        await status.edit_text(f"⚠️ {exc}")
        return
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка парсинга CSV")
        await status.edit_text("⚠️ Не удалось прочитать файл. Проверьте формат.")
        return

    pipeline = _build_pipeline(settings, provider)
    # Категоризация может ходить в сеть (LLM) — уводим в поток.
    stats = await asyncio.to_thread(pipeline.run, transactions)
    added = await asyncio.to_thread(db.save_transactions, message.from_user.id, transactions)

    by_cat = Counter(tx.category for tx in transactions)
    lines = [
        f"✅ Обработано операций: *{len(transactions)}* (новых: {added})",
        f"📖 Правилами: *{stats.rules_share * 100:.0f}%*"
        + (f", через LLM: {stats.by_llm}" if stats.by_llm else "")
        + (f", по умолчанию: {stats.by_default}" if stats.by_default else ""),
        "",
        "*Категории:*",
    ]
    for cat in CATEGORIES:
        if by_cat.get(cat):
            lines.append(f"• {cat}: {by_cat[cat]} шт.")
    lines.append("\nОтчёт за неделю — /report")
    await status.edit_text("\n".join(lines), parse_mode="Markdown")


@router.message(Command("report"))
async def cmd_report(
    message: Message,
    db: Database,
    provider: LLMProvider | None,
) -> None:
    """Еженедельный отчёт со сравнением и наблюдениями."""
    ref = _latest_date(db, message.from_user.id) or date.today()
    report = await asyncio.to_thread(build_report, db, message.from_user.id, ref, provider)
    await message.answer(format_report(report), parse_mode="Markdown")


@router.message(Command("fix"))
async def cmd_fix(message: Message, db: Database) -> None:
    """Показать последние операции для ручной правки категории."""
    rows = await asyncio.to_thread(db.recent_transactions, message.from_user.id, 10)
    if not rows:
        await message.answer("Пока нет операций. Сначала пришлите CSV-выписку.")
        return
    await message.answer(
        "Выберите операцию, у которой нужно поправить категорию:",
        reply_markup=recent_transactions_keyboard(rows),
    )


@router.callback_query(F.data.startswith("pick:"))
async def on_pick(callback: CallbackQuery) -> None:
    tx_id = int(callback.data.split(":")[1])
    await callback.message.edit_text(
        "Выберите правильную категорию:",
        reply_markup=categories_keyboard(tx_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setcat:"))
async def on_set_category(callback: CallbackQuery, db: Database) -> None:
    _, tx_id_str, category = callback.data.split(":", 2)
    if category not in CATEGORIES:
        await callback.answer("Неизвестная категория", show_alert=True)
        return
    ok = await asyncio.to_thread(
        db.update_category, callback.from_user.id, int(tx_id_str), category
    )
    if ok:
        await callback.message.edit_text(f"✅ Категория изменена на «{category}».")
    else:
        await callback.message.edit_text("⚠️ Операция не найдена.")
    await callback.answer()


def _latest_date(db: Database, user_id: int) -> date | None:
    rows = db.recent_transactions(user_id, 1)
    if not rows:
        return None
    return date.fromisoformat(rows[0]["op_date"])
