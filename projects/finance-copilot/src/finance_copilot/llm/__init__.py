"""Абстракция над LLM-провайдерами (YandexGPT / GigaChat).

Категоризатор и генератор наблюдений зависят только от интерфейса
LLMProvider, а не от конкретного провайдера — так их легко подменять.
"""

from __future__ import annotations

from ..config import Settings
from .base import LLMProvider


def build_provider(settings: Settings) -> LLMProvider | None:
    """Фабрика провайдера по настройкам. None -> LLM отключён."""
    name = (settings.llm_provider or "none").lower()
    if name == "none":
        return None
    if name == "yandex":
        from .yandex import YandexGPTProvider

        return YandexGPTProvider(
            api_key=settings.yandex_api_key,
            folder_id=settings.yandex_folder_id,
            model=settings.yandex_model,
        )
    if name == "gigachat":
        from .gigachat import GigaChatProvider

        return GigaChatProvider(
            auth_key=settings.gigachat_auth_key,
            scope=settings.gigachat_scope,
        )
    raise ValueError(f"Неизвестный LLM_PROVIDER: {settings.llm_provider}")


__all__ = ["LLMProvider", "build_provider"]
