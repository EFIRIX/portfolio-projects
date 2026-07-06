"""Загрузка конфигурации из окружения и YAML-файлов."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

# Корень проекта = на два уровня выше этого файла (src/finance_copilot/config.py)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"

CATEGORY_RULES_PATH = CONFIG_DIR / "category_rules.yaml"
BANK_FORMATS_PATH = CONFIG_DIR / "bank_formats.yaml"


@dataclass
class Settings:
    bot_token: str
    db_path: str
    llm_provider: str
    llm_batch_size: int
    log_level: str

    # YandexGPT
    yandex_api_key: str
    yandex_folder_id: str
    yandex_model: str

    # GigaChat
    gigachat_auth_key: str
    gigachat_scope: str


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@lru_cache
def get_settings() -> Settings:
    """Читает настройки из переменных окружения (.env подхватывается в bot.main)."""
    return Settings(
        bot_token=_get("BOT_TOKEN"),
        db_path=_get("DB_PATH", "finance_copilot.db"),
        llm_provider=_get("LLM_PROVIDER", "none").lower(),
        llm_batch_size=int(_get("LLM_BATCH_SIZE", "25") or "25"),
        log_level=_get("LOG_LEVEL", "INFO").upper(),
        yandex_api_key=_get("YANDEX_API_KEY"),
        yandex_folder_id=_get("YANDEX_FOLDER_ID"),
        yandex_model=_get("YANDEX_MODEL", "lite"),
        gigachat_auth_key=_get("GIGACHAT_AUTH_KEY"),
        gigachat_scope=_get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
    )


@lru_cache
def load_category_rules() -> dict[str, list[str]]:
    """Возвращает {категория: [ключевые слова...]} из category_rules.yaml."""
    with CATEGORY_RULES_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw = data.get("категории", {}) or {}
    # Нормализуем ключевые слова в нижний регистр один раз при загрузке.
    return {
        category: [str(kw).lower() for kw in (keywords or [])]
        for category, keywords in raw.items()
    }


@lru_cache
def load_bank_formats() -> dict[str, dict]:
    """Возвращает {имя_формата: описание_формата} из bank_formats.yaml."""
    with BANK_FORMATS_PATH.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("форматы", {}) or {}
