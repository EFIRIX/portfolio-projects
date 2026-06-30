import asyncio
from pathlib import Path
from types import SimpleNamespace

from services.socks_feed import (
    dedupe_socks_proxies,
    extract_socks_proxies,
    parse_socks_proxy,
    refresh_socks_feed,
    safe_socks_proxy_url_from_row,
    socks_status_text,
)
from storage.database import Database


def test_parse_socks_url_with_auth():
    candidate = parse_socks_proxy("socks5://user:pass@proxy.example.com:1080", "test")
    assert candidate.scheme == "socks5"
    assert candidate.host == "proxy.example.com"
    assert candidate.username == "user"
    assert candidate.password == "pass"


def test_parse_http_url():
    candidate = parse_socks_proxy("http://127.0.0.1:8080", "test")
    assert candidate.scheme == "http"
    assert candidate.host == "127.0.0.1"
    assert candidate.port == 8080


def test_parse_host_port_defaults_to_socks5():
    candidate = parse_socks_proxy("proxy.example.com:1080", "test")
    assert candidate.scheme == "socks5"
    assert candidate.host == "proxy.example.com"


def test_extract_and_dedupe_socks_proxies():
    text = "socks5://proxy.example.com:1080\nproxy.example.com:1080\nhttp://host.test:8080"
    candidates = extract_socks_proxies(text, "feed")
    assert len(candidates) == 2
    assert len(dedupe_socks_proxies(candidates + candidates)) == 2


def test_database_socks_proxy_candidate(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_socks_proxy_candidate(
        {
            "scheme": "socks5",
            "host": "proxy.example.com",
            "port": 1080,
            "username": "user",
            "password": "pass",
            "source": "test",
        }
    )
    db.update_socks_proxy_check("socks5", "proxy.example.com", 1080, "user", "pass", True, 200)
    row = db.socks_proxy_candidates(1)[0]
    assert row["is_active"] == 1
    assert db.socks_proxy_summary()["active"] == 1
    assert safe_socks_proxy_url_from_row(row) == "socks5://user:***@proxy.example.com:1080"


def test_refresh_socks_feed_from_seed(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    settings = SimpleNamespace(
        socks_feed_enabled=True,
        socks_seed_proxies=["socks5://proxy.example.com:1080"],
        socks_feed_urls=[],
        socks_max_candidates=100,
    )
    result = asyncio.run(refresh_socks_feed(settings, db))
    assert result.found == 1
    assert db.socks_proxy_summary()["total"] == 1


def test_socks_status_masks_password(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.set_setting("global", "socks:selected_proxy", "socks5://user:***@proxy.example.com:1080")
    text = socks_status_text(None, db)
    assert "pass" not in text
