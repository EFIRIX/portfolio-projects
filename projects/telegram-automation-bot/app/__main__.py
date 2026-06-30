from __future__ import annotations

import asyncio
import logging
import signal
import sys
from contextlib import suppress

import uvicorn

from app.config import ensure_directories, load_settings
from app.secure_setup import (
    load_existing_for_setup,
    maybe_print_config,
    reset_config,
    run_setup_wizard,
    setup_is_required,
)
from bot.runner import run_bot
from services.secure_config import is_windows_onefile
from services.platform_checks import run_platform_checks
from storage.database import Database
from web.server import create_web_app


async def main() -> None:
    settings = load_settings()
    if setup_is_required(settings):
        run_setup_wizard(load_existing_for_setup())
        return

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    ensure_directories([settings.media_dir, settings.project_root / "data", settings.project_root / "logs"])
    db = Database.from_url(settings.database_url, settings.project_root)
    db.initialize()

    report = run_platform_checks(settings)
    for item in report.items:
        db.log_event("INFO" if item.ok else "WARNING", "platform_check", None, None, None, item.as_dict())

    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is empty. Set it in .env for dev mode or open TelegramAutomationBot.exe GUI on Windows.")
    if not settings.owner_ids:
        raise SystemExit("OWNER_IDS is empty. Set it in .env for dev mode or open TelegramAutomationBot.exe GUI on Windows.")

    web_app = create_web_app(settings, db, report)
    uvicorn_config = uvicorn.Config(
        web_app,
        host=settings.web_host,
        port=settings.web_port,
        log_level=settings.log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(uvicorn_config)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    web_task = asyncio.create_task(server.serve(), name="web")
    bot_task = asyncio.create_task(run_bot(settings, db, report), name="bot")
    stop_task = asyncio.create_task(stop_event.wait(), name="stop")

    done, pending = await asyncio.wait(
        {web_task, bot_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in done:
        if task is not stop_task:
            task.result()

    server.should_exit = True
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


if __name__ == "__main__":
    if "--gui" in sys.argv or (
        is_windows_onefile()
        and "--run-bot" not in sys.argv
        and (len(sys.argv) == 1 or "--setup" in sys.argv)
    ):
        from app.gui import run_gui

        run_gui()
        raise SystemExit(0)
    if "--reset-config" in sys.argv:
        reset_config()
        raise SystemExit(0)
    if "--show-config" in sys.argv:
        maybe_print_config()
        raise SystemExit(0)
    if "--setup" in sys.argv:
        run_setup_wizard(load_existing_for_setup())
        raise SystemExit(0)
    asyncio.run(main())
