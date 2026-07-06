"""Провайдер GigaChat (Sber).

Док: https://developers.sber.ru/docs/ru/gigachat/api/overview
Аутентификация: по Authorization Key получаем короткоживущий access_token,
затем ходим в chat/completions. Токен кэшируем в памяти до истечения.
"""

from __future__ import annotations

import logging
import time
import uuid

import requests

from .base import LLMProvider

logger = logging.getLogger(__name__)

_OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"


class GigaChatProvider(LLMProvider):
    name = "gigachat"

    def __init__(
        self,
        auth_key: str,
        scope: str = "GIGACHAT_API_PERS",
        model: str = "GigaChat",
        timeout: int = 30,
        verify_ssl: bool = True,
    ) -> None:
        if not auth_key:
            raise ValueError("Для GigaChat нужен GIGACHAT_AUTH_KEY")
        self.auth_key = auth_key
        self.scope = scope
        self.model = model
        self.timeout = timeout
        # В корпоративных сетях иногда требуется цепочка сертификатов Минцифры;
        # verify_ssl оставлен настраиваемым, но по умолчанию проверка включена.
        self.verify_ssl = verify_ssl
        self._token: str | None = None
        self._token_exp: float = 0.0

    def _ensure_token(self) -> str:
        if self._token and time.monotonic() < self._token_exp:
            return self._token
        headers = {
            "Authorization": f"Basic {self.auth_key}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        }
        resp = requests.post(
            _OAUTH_URL,
            headers=headers,
            data={"scope": self.scope},
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        # expires_at приходит в миллисекундах epoch; берём запас 30 сек.
        self._token_exp = time.monotonic() + 1500
        return self._token

    def complete(self, prompt: str, system: str | None = None) -> str:
        token = self._ensure_token()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": self.model, "messages": messages, "temperature": 0.2}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            _CHAT_URL,
            json=payload,
            headers=headers,
            timeout=self.timeout,
            verify=self.verify_ssl,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
