from __future__ import annotations

import asyncio

from telethon import TelegramClient

from app.config import load_settings


async def main() -> None:
    settings = load_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first.")

    client = TelegramClient(
        str(settings.telethon_user_session),
        settings.telegram_api_id,
        settings.telegram_api_hash,
        timeout=settings.telegram_connect_timeout,
    )
    await client.start()
    try:
        me = await client.get_me()
        print(f"Telethon user session saved: {settings.telethon_user_session}")
        print(f"Authorized as: {getattr(me, 'username', None) or getattr(me, 'first_name', None) or me.id}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
