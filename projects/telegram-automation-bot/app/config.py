from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - dependency is installed in runtime env
    dotenv_values = None

from services.secure_config import app_data_dir, load_secure_config, should_use_secure_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _dotenv_config() -> Dict[str, str]:
    env_path = PROJECT_ROOT / ".env"
    if dotenv_values is None or not env_path.exists():
        return {}
    return {key: str(value) for key, value in dotenv_values(env_path).items() if value is not None}


def runtime_project_root() -> Path:
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        return app_data_dir()
    return PROJECT_ROOT


def _parse_owner_ids(raw: str) -> List[int]:
    ids: List[int] = []
    for chunk in raw.replace(";", ",").split(","):
        value = chunk.strip()
        if not value:
            continue
        ids.append(int(value))
    return ids


def _parse_optional_int(raw: str) -> Optional[int]:
    value = raw.strip()
    if not value:
        return None
    return int(value.strip("{}"))


def _resolve_path(raw: str, default: str, project_root: Path) -> Path:
    value = Path(raw or default)
    if not value.is_absolute():
        value = project_root / value
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    owner_ids: List[int]
    admin_password: str
    database_url: str
    media_dir: Path
    web_host: str
    web_port: int
    archive_channel_id: Optional[int]
    archive_group_id: Optional[int]
    archive_mode: str
    network_mode: str
    bot_api_base_urls: List[str]
    telegram_proxy_urls: List[str]
    telegram_connect_timeout: int
    telegram_retry_min_seconds: int
    telegram_retry_max_seconds: int
    socks_feed_enabled: bool
    socks_feed_refresh_seconds: int
    socks_feed_urls: List[str]
    socks_seed_proxies: List[str]
    socks_max_candidates: int
    mtproxy_enabled: bool
    mtproxy_refresh_seconds: int
    mtproxy_feed_urls: List[str]
    mtproxy_channels: List[str]
    mtproxy_seed_proxies: List[str]
    mtproxy_max_candidates: int
    telegram_api_id: Optional[int]
    telegram_api_hash: str
    telethon_bot_session: Path
    telethon_user_session: Path
    telethon_user_feed_enabled: bool
    log_level: str
    project_root: Path

    def is_owner(self, user_id: Optional[int]) -> bool:
        return user_id is not None and user_id in self.owner_ids

    def owner_ids_text(self) -> str:
        return ", ".join(str(owner_id) for owner_id in self.owner_ids) or "not configured"


def load_settings() -> Settings:
    project_root = runtime_project_root()
    secure_values = load_secure_config() if should_use_secure_config() else {}
    dotenv_values_map = _dotenv_config()

    def value(key: str, default: str = "") -> str:
        if key in os.environ:
            return os.environ[key]
        if key in secure_values:
            return secure_values[key]
        return dotenv_values_map.get(key, default)

    database_url = value("DATABASE_URL", "sqlite:///./data/bot.sqlite3")
    media_dir = _resolve_path(value("MEDIA_DIR", "./media"), "./media", project_root)
    owner_ids = _parse_owner_ids(value("OWNER_IDS", ""))

    return Settings(
        bot_token=value("BOT_TOKEN", "").strip(),
        owner_ids=owner_ids,
        admin_password=value("ADMIN_PASSWORD", "change-me"),
        database_url=database_url,
        media_dir=media_dir,
        web_host=value("WEB_HOST", "127.0.0.1"),
        web_port=int(value("WEB_PORT", "8000")),
        archive_channel_id=_parse_optional_int(value("ARCHIVE_CHANNEL_ID", "")),
        archive_group_id=_parse_optional_int(value("ARCHIVE_GROUP_ID", "")),
        archive_mode=value("ARCHIVE_MODE", "channel").strip().lower() or "channel",
        network_mode=value("NETWORK_MODE", "auto").strip().lower() or "auto",
        bot_api_base_urls=_parse_csv(value("BOT_API_BASE_URLS", "https://api.telegram.org")),
        telegram_proxy_urls=_parse_csv(value("TELEGRAM_PROXY_URLS", "")),
        telegram_connect_timeout=int(value("TELEGRAM_CONNECT_TIMEOUT", "10")),
        telegram_retry_min_seconds=int(value("TELEGRAM_RETRY_MIN_SECONDS", "5")),
        telegram_retry_max_seconds=int(value("TELEGRAM_RETRY_MAX_SECONDS", "120")),
        socks_feed_enabled=_parse_bool(value("SOCKS_FEED_ENABLED", "1")),
        socks_feed_refresh_seconds=int(value("SOCKS_FEED_REFRESH_SECONDS", "900")),
        socks_feed_urls=_parse_csv(value("SOCKS_FEED_URLS", "")),
        socks_seed_proxies=_parse_csv(value("SOCKS_SEED_PROXIES", "")),
        socks_max_candidates=int(value("SOCKS_MAX_CANDIDATES", "100")),
        mtproxy_enabled=_parse_bool(value("MTPROXY_ENABLED", "0")),
        mtproxy_refresh_seconds=int(value("MTPROXY_REFRESH_SECONDS", "900")),
        mtproxy_feed_urls=_parse_csv(value("MTPROXY_FEED_URLS", "https://t.me/s/ProxyMTProto")),
        mtproxy_channels=_parse_csv(value("MTPROXY_CHANNELS", "ProxyMTProto")),
        mtproxy_seed_proxies=_parse_csv(value("MTPROXY_SEED_PROXIES", "")),
        mtproxy_max_candidates=int(value("MTPROXY_MAX_CANDIDATES", "50")),
        telegram_api_id=_parse_optional_int(value("TELEGRAM_API_ID", "")),
        telegram_api_hash=value("TELEGRAM_API_HASH", "").strip(),
        telethon_bot_session=_resolve_path(value("TELETHON_BOT_SESSION", "./data/telethon-bot.session"), "./data/telethon-bot.session", project_root),
        telethon_user_session=_resolve_path(value("TELETHON_USER_SESSION", "./data/telethon-user.session"), "./data/telethon-user.session", project_root),
        telethon_user_feed_enabled=_parse_bool(value("TELETHON_USER_FEED_ENABLED", "0")),
        log_level=value("LOG_LEVEL", "INFO").upper(),
        project_root=project_root,
    )


def ensure_directories(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def _parse_csv(raw: str) -> List[str]:
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}
