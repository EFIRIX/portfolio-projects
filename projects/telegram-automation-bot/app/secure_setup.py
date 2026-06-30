from __future__ import annotations

import getpass
import secrets
import string
from typing import Iterable

from services.secure_config import (
    default_secure_config_path,
    delete_secure_config,
    is_windows_onefile,
    masked_secure_config,
    save_secure_config,
    should_use_secure_config,
)


REQUIRED_KEYS = ("BOT_TOKEN", "OWNER_IDS")

DEFAULTS = {
    "ADMIN_PASSWORD": "",
    "ARCHIVE_GROUP_ID": "",
    "ARCHIVE_CHANNEL_ID": "",
    "ARCHIVE_MODE": "forum",
    "DATABASE_URL": "sqlite:///./data/bot.sqlite3",
    "MEDIA_DIR": "./media",
    "WEB_HOST": "127.0.0.1",
    "WEB_PORT": "8000",
    "NETWORK_MODE": "auto",
    "BOT_API_BASE_URLS": "https://api.telegram.org",
    "TELEGRAM_PROXY_URLS": "",
    "TELEGRAM_CONNECT_TIMEOUT": "10",
    "TELEGRAM_RETRY_MIN_SECONDS": "5",
    "TELEGRAM_RETRY_MAX_SECONDS": "120",
    "SOCKS_FEED_ENABLED": "1",
    "SOCKS_FEED_REFRESH_SECONDS": "900",
    "SOCKS_FEED_URLS": "",
    "SOCKS_SEED_PROXIES": "",
    "SOCKS_MAX_CANDIDATES": "100",
    "MTPROXY_ENABLED": "0",
    "LOG_LEVEL": "INFO",
}


def setup_is_required(settings) -> bool:
    return is_windows_onefile() and (not settings.bot_token or not settings.owner_ids)


def maybe_print_config() -> None:
    config = masked_secure_config()
    print(f"Secure config: {default_secure_config_path()}")
    if not config:
        print("No secure config saved yet.")
        return
    for key in sorted(config):
        print(f"{key}={config[key]}")


def reset_config() -> None:
    delete_secure_config()
    print(f"Deleted secure config: {default_secure_config_path()}")


def run_setup_wizard(existing: dict[str, str] | None = None) -> None:
    existing = existing or {}
    print("TelegramAutomationBot first-run setup")
    print(f"Secure config will be stored here: {default_secure_config_path()}")
    print("Secrets are protected with Windows DPAPI for the current Windows user.")
    print()

    values = dict(DEFAULTS)
    values.update(existing)

    token = prompt_secret("BOT_TOKEN from @BotFather", values.get("BOT_TOKEN", ""), required=True)
    owner_ids = prompt_text("OWNER_IDS, for example 994582601", values.get("OWNER_IDS", ""), required=True)
    admin_password = prompt_secret(
        "ADMIN_PASSWORD for local web admin (leave empty to generate)",
        values.get("ADMIN_PASSWORD", ""),
        required=False,
    )
    if not admin_password:
        admin_password = generate_password()
        print(f"Generated ADMIN_PASSWORD: {admin_password}")

    values.update(
        {
            "BOT_TOKEN": token,
            "OWNER_IDS": owner_ids,
            "ADMIN_PASSWORD": admin_password,
            "ARCHIVE_GROUP_ID": prompt_text("ARCHIVE_GROUP_ID (optional, -100...)", values.get("ARCHIVE_GROUP_ID", "")),
            "ARCHIVE_CHANNEL_ID": prompt_text("ARCHIVE_CHANNEL_ID fallback (optional, -100...)", values.get("ARCHIVE_CHANNEL_ID", "")),
            "SOCKS_SEED_PROXIES": prompt_text(
                "SOCKS_SEED_PROXIES (optional, comma-separated)",
                values.get("SOCKS_SEED_PROXIES", ""),
            ),
            "SOCKS_FEED_URLS": prompt_text(
                "SOCKS_FEED_URLS (optional, comma-separated raw lists)",
                values.get("SOCKS_FEED_URLS", ""),
            ),
        }
    )

    save_secure_config(values)
    print()
    print("Saved. Start TelegramAutomationBot.exe again to launch the bot.")


def load_existing_for_setup() -> dict[str, str]:
    if not should_use_secure_config():
        return {}
    from services.secure_config import load_secure_config

    return load_secure_config()


def prompt_text(label: str, default: str = "", required: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{label}{suffix}: ").strip()
        if not value and default:
            value = default
        if value or not required:
            return value
        print("This value is required.")


def prompt_secret(label: str, default: str = "", required: bool = False) -> str:
    suffix = " [saved]" if default else ""
    while True:
        value = getpass.getpass(f"{label}{suffix}: ").strip()
        if not value and default:
            value = default
        if value or not required:
            return value
        print("This value is required.")


def generate_password(length: int = 18) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def should_handle_cli(args: Iterable[str]) -> bool:
    return any(arg in {"--setup", "--show-config", "--reset-config"} for arg in args)
