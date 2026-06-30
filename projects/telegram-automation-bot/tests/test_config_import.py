from pathlib import Path

import pytest

from app.config_import import ConfigImportError, load_import_config, masked_import_config, merge_import_config


def test_load_json_import_config(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text(
        """
        {
          "version": 1,
          "BOT_TOKEN": "123456789:test-token",
          "OWNER_IDS": "994582601",
          "ARCHIVE_GROUP_ID": "-1001",
          "UNKNOWN": "ignored"
        }
        """,
        encoding="utf-8",
    )

    values = load_import_config(path)

    assert values["BOT_TOKEN"] == "123456789:test-token"
    assert values["OWNER_IDS"] == "994582601"
    assert values["ARCHIVE_GROUP_ID"] == "-1001"
    assert "UNKNOWN" not in values


def test_load_env_import_config(tmp_path: Path):
    path = tmp_path / "config.env"
    path.write_text(
        "\n".join(
            [
                "BOT_TOKEN=123456789:test-token",
                "OWNER_IDS=994582601",
                "ARCHIVE_MODE=forum",
            ]
        ),
        encoding="utf-8",
    )

    values = load_import_config(path)

    assert values["BOT_TOKEN"] == "123456789:test-token"
    assert values["OWNER_IDS"] == "994582601"
    assert values["ARCHIVE_MODE"] == "forum"


def test_import_requires_token_and_owner(tmp_path: Path):
    path = tmp_path / "config.json"
    path.write_text('{"BOT_TOKEN": "token"}', encoding="utf-8")

    with pytest.raises(ConfigImportError):
        load_import_config(path)


def test_merge_import_config_keeps_defaults():
    values = merge_import_config({"ADMIN_PASSWORD": "old"}, {"BOT_TOKEN": "token", "OWNER_IDS": "1"})

    assert values["ADMIN_PASSWORD"] == "old"
    assert values["BOT_TOKEN"] == "token"
    assert values["NETWORK_MODE"] == "auto"


def test_masked_import_config_hides_secret_values():
    masked = masked_import_config(
        {
            "BOT_TOKEN": "example-bot-token",
            "TELEGRAM_PROXY_URLS": "socks5://user:pass@proxy.example.com:1080",
        }
    )

    assert "example-bot-token" not in masked["BOT_TOKEN"]
    assert "pass" not in masked["TELEGRAM_PROXY_URLS"]
