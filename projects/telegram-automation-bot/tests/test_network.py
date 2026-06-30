import asyncio
from pathlib import Path
from types import SimpleNamespace

from aiogram.exceptions import TelegramNetworkError, TelegramUnauthorizedError
import pytest

from services import network
from storage.database import Database


def make_settings(**overrides):
    data = {
        "bot_token": "123456:testtoken",
        "network_mode": "auto",
        "bot_api_base_urls": ["https://api.telegram.org", "https://tg.example.com"],
        "telegram_proxy_urls": ["socks5://user:pass@127.0.0.1:1080"],
        "telegram_connect_timeout": 10,
        "telegram_retry_min_seconds": 1,
        "telegram_retry_max_seconds": 2,
        "socks_max_candidates": 100,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_mask_proxy_url_hides_password():
    assert network.mask_proxy_url("socks5://user:pass@example.com:1080") == "socks5://user:***@example.com:1080"


def test_build_network_routes_auto_order():
    routes = network.build_network_routes(make_settings())
    assert [route.label for route in routes] == ["direct", "custom_api", "proxy", "custom_api+proxy"]
    assert routes[1].base_url == "https://tg.example.com"


def test_fatal_and_retryable_errors():
    assert network.is_fatal_network_error(TelegramUnauthorizedError(method=None, message="bad token"))
    assert network.is_retryable_network_error(TelegramNetworkError(method=None, message="timeout"))


def test_choose_working_bot_falls_back_to_custom_api(monkeypatch, tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    calls = []

    class FakeSession:
        async def close(self):
            return None

    class FakeBot:
        def __init__(self, route):
            self.route = route
            self.session = FakeSession()

        async def get_me(self):
            calls.append(self.route.label)
            if self.route.label == "direct":
                raise TelegramNetworkError(method=None, message="timeout")
            return SimpleNamespace(id=1)

    def fake_create_bot(settings, route):
        return FakeBot(route)

    monkeypatch.setattr(network, "create_bot", fake_create_bot)
    selection = asyncio.run(network.choose_working_bot(make_settings(telegram_proxy_urls=[]), db))
    assert calls == ["direct", "custom_api"]
    assert selection.route.label == "custom_api"
    assert "pass" not in db.get_setting("global", "network:selected_route", default="")


def test_choose_working_bot_records_all_failed(monkeypatch, tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()

    class FakeSession:
        async def close(self):
            return None

    class FakeBot:
        session = FakeSession()

        async def get_me(self):
            raise TelegramNetworkError(method=None, message="timeout")

    monkeypatch.setattr(network, "create_bot", lambda settings, route: FakeBot())
    with pytest.raises(network.NetworkUnavailable):
        asyncio.run(network.choose_working_bot(make_settings(bot_api_base_urls=["https://api.telegram.org"], telegram_proxy_urls=[]), db))
    assert "timeout" in db.get_setting("global", "network:last_error", default="")


def test_build_network_routes_includes_db_socks_candidate(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_socks_proxy_candidate(
        {
            "scheme": "socks5",
            "host": "proxy.test",
            "port": 1080,
            "username": "user",
            "password": "pass",
            "source": "test",
        }
    )
    routes = network.build_network_routes(make_settings(telegram_proxy_urls=[]), db)
    assert routes[-1].proxy_url == "socks5://user:pass@proxy.test:1080"
    assert "pass" not in routes[-1].safe_name()
