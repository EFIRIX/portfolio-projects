"""Точка входа бота: настройка окружения, DI, запуск polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from ..config import get_settings
from ..db import Database
from ..llm import build_provider
from ..security import install_log_filter
from . import handlers


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Последний рубеж: маскируем возможные PAN/счета в логах.
    install_log_filter()


async def run() -> None:
    load_dotenv()
    settings = get_settings()
    _setup_logging(settings.log_level)
    log = logging.getLogger(__name__)

    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан. Скопируйте .env.example в .env и заполните.")

    db = Database(settings.db_path)
    try:
        provider = build_provider(settings)
    except ValueError as exc:
        log.warning("LLM недоступен (%s). Работаю только на правилах.", exc)
        provider = None

    log.info(
        "Старт бота. LLM: %s",
        provider.name if provider else "отключён (только правила)",
    )

    bot = Bot(token=settings.bot_token)
    dp = Dispatcher()
    dp.include_router(handlers.router)

    # DI: значения прокидываются в хендлеры по имени параметра.
    await dp.start_polling(bot, db=db, settings=settings, provider=provider)


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit) as exc:
        logging.getLogger(__name__).info("Остановка: %s", exc)


if __name__ == "__main__":
    main()
