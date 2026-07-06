"""Абстрактный интерфейс LLM-провайдера."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Единый интерфейс к разным LLM (YandexGPT, GigaChat, ...).

    Реализации отвечают за аутентификацию и формат запроса конкретного API,
    но наружу отдают простой синхронный текстовый complete().
    """

    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> str:
        """Возвращает текстовый ответ модели на prompt (+ опциональный system)."""
        raise NotImplementedError
