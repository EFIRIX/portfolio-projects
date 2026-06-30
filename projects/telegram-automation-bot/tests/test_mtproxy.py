from pathlib import Path
from types import SimpleNamespace

from services.mtproxy_feed import dedupe_candidates, extract_proxy_candidates, parse_proxy_candidate, refresh_mtproxy_feed
from services.mtproxy_runtime import mtproxy_status_text
from storage.database import Database


def test_parse_tg_proxy_url():
    candidate = parse_proxy_candidate("tg://proxy?server=1.2.3.4&port=443&secret=ddabcdefabcdefabcdefabcdefabcdefab", "test")
    assert candidate.host == "1.2.3.4"
    assert candidate.port == 443
    assert candidate.secret.startswith("dd")


def test_parse_manual_proxy():
    candidate = parse_proxy_candidate("proxy.example.com:443:abcdefabcdefabcdefabcdefabcdefab", "manual")
    assert candidate.host == "proxy.example.com"
    assert candidate.port == 443


def test_extract_proxy_candidates_from_html():
    text = '<a href="tg://proxy?server=host.test&amp;port=443&amp;secret=abcdefabcdefabcdefabcdefabcdefab">connect</a>'
    candidates = extract_proxy_candidates(text, "html")
    assert len(candidates) == 1
    assert candidates[0].host == "host.test"


def test_dedupe_candidates():
    candidate = parse_proxy_candidate("host.test:443:abcdefabcdefabcdefabcdefabcdefab", "one")
    assert len(dedupe_candidates([candidate, candidate])) == 1


def test_database_mtproxy_candidates(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_mtproxy_candidate(
        {
            "host": "host.test",
            "port": 443,
            "secret": "abcdefabcdefabcdefabcdefabcdefab",
            "source": "test",
            "raw_url": "tg://proxy",
        }
    )
    db.update_mtproxy_check("host.test", 443, "abcdefabcdefabcdefabcdefabcdefab", True, 123)
    assert db.mtproxy_summary()["active"] == 1
    assert db.mtproxy_candidates(1)[0]["latency_ms"] == 123


def test_mtproxy_status_without_settings(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    text = mtproxy_status_text(None, db)
    assert "MTProxy" in text


def test_refresh_mtproxy_feed_from_seed(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    settings = SimpleNamespace(
        mtproxy_enabled=True,
        mtproxy_seed_proxies=["host.test:443:abcdefabcdefabcdefabcdefabcdefab"],
        mtproxy_feed_urls=[],
        telethon_user_feed_enabled=False,
        mtproxy_max_candidates=50,
    )
    import asyncio

    result = asyncio.run(refresh_mtproxy_feed(settings, db))
    assert result.found == 1
    assert db.mtproxy_summary()["total"] == 1
