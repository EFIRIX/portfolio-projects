from pathlib import Path
from types import SimpleNamespace

from app import config
from app import secure_setup
from services import secure_config


def test_secure_config_roundtrip_and_masking(tmp_path: Path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setenv("TELEGRAM_AUTOMATION_SECURE_CONFIG_PATH", str(config_path))

    secure_config.save_secure_config(
        {
            "BOT_TOKEN": "example-bot-token",
            "OWNER_IDS": "994582601",
            "TELEGRAM_PROXY_URLS": "socks5://user:pass@proxy.example.com:1080",
        }
    )

    loaded = secure_config.load_secure_config()
    assert loaded["BOT_TOKEN"] == "example-bot-token"
    assert loaded["OWNER_IDS"] == "994582601"
    assert "example-bot-token" not in config_path.read_text(encoding="utf-8")

    masked = secure_config.masked_secure_config()
    assert "example-bot-token" not in masked["BOT_TOKEN"]
    assert "pass" not in masked["TELEGRAM_PROXY_URLS"]


def test_config_precedence_env_secure_dotenv(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "BOT_TOKEN=dotenv-token",
                "OWNER_IDS=111",
                "ADMIN_PASSWORD=dotenv-password",
                "MEDIA_DIR=./dotenv-media",
            ]
        ),
        encoding="utf-8",
    )
    secure_path = tmp_path / "secure.json"
    monkeypatch.setenv("TELEGRAM_AUTOMATION_SECURE_CONFIG_PATH", str(secure_path))
    secure_config.save_secure_config(
        {
            "BOT_TOKEN": "secure-token",
            "OWNER_IDS": "222",
            "ADMIN_PASSWORD": "secure-password",
            "MEDIA_DIR": "./secure-media",
        }
    )
    monkeypatch.setenv("BOT_TOKEN", "env-token")

    settings = config.load_settings()

    assert settings.bot_token == "env-token"
    assert settings.owner_ids == [222]
    assert settings.admin_password == "secure-password"
    assert settings.media_dir == tmp_path / "secure-media"


def test_setup_required_only_for_windows_onefile(monkeypatch):
    monkeypatch.setattr(secure_setup, "is_windows_onefile", lambda: True)
    assert secure_setup.setup_is_required(SimpleNamespace(bot_token="", owner_ids=[]))
    assert not secure_setup.setup_is_required(SimpleNamespace(bot_token="token", owner_ids=[1]))
