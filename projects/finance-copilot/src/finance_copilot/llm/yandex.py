"""Провайдер YandexGPT (Foundation Models, completion API).

Док: https://yandex.cloud/ru/docs/foundation-models/concepts/yandexgpt/
"""

from __future__ import annotations

import logging

import requests

from .base import LLMProvider

logger = logging.getLogger(__name__)

_ENDPOINT = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


class YandexGPTProvider(LLMProvider):
    name = "yandex"

    def __init__(
        self,
        api_key: str,
        folder_id: str,
        model: str = "lite",
        timeout: int = 30,
    ) -> None:
        if not api_key or not folder_id:
            raise ValueError("Для YandexGPT нужны YANDEX_API_KEY и YANDEX_FOLDER_ID")
        self.api_key = api_key
        self.folder_id = folder_id
        self.model = model
        self.timeout = timeout

    @property
    def _model_uri(self) -> str:
        return f"gpt://{self.folder_id}/yandexgpt-{self.model}/latest"

    def complete(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "text": system})
        messages.append({"role": "user", "text": prompt})

        payload = {
            "modelUri": self._model_uri,
            "completionOptions": {"stream": False, "temperature": 0.2, "maxTokens": 2000},
            "messages": messages,
        }
        headers = {
            "Authorization": f"Api-Key {self.api_key}",
            "x-folder-id": self.folder_id,
            "Content-Type": "application/json",
        }
        resp = requests.post(_ENDPOINT, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["result"]["alternatives"][0]["message"]["text"]
