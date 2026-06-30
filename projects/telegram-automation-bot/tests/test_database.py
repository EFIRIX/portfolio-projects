from pathlib import Path

from storage.database import Database


def test_database_message_and_settings(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_message(
        {
            "chat_id": 1,
            "message_id": 2,
            "user_id": 3,
            "username": "owner",
            "text": "hello",
            "caption": None,
            "media_type": None,
            "file_id": None,
            "file_path": None,
            "raw_json": "{}",
        }
    )
    assert db.get_message(1, 2)["text"] == "hello"
    db.set_setting("chat_user", "muted", "1", chat_id=1, user_id=3)
    assert db.get_setting("chat_user", "muted", chat_id=1, user_id=3) == "1"
    assert db.count("messages") == 1


def test_business_connection_summary(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_business_connection(
        {
            "connection_id": "abc",
            "user_id": 42,
            "user_chat_id": 43,
            "is_enabled": True,
            "can_reply": True,
            "raw": {"id": "abc"},
        }
    )
    summary = db.business_summary()
    assert summary["enabled"] is True
    assert summary["can_reply"] is True
    assert db.count("business_connections") == 1


def test_archive_mapping(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.save_archive_mapping(
        {
            "source_chat_id": 10,
            "source_message_id": 20,
            "source_user_id": 30,
            "username": "tester",
            "display_name": "Tester",
            "media_type": "photo",
            "archive_chat_id": -100123,
            "archive_thread_id": 777,
            "archive_message_id": 40,
            "archive_mode": "forum",
        }
    )
    item = db.get_archive_mapping(10, 20)
    assert item["archive_message_id"] == 40
    assert item["archive_thread_id"] == 777
    assert item["archive_mode"] == "forum"
    assert db.archive_summary()["total"] == 1


def test_archive_thread_mapping(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.save_archive_thread(
        {
            "source_chat_id": 10,
            "source_user_id": 30,
            "title": "@tester · 10",
            "archive_group_id": -100999,
            "message_thread_id": 777,
        }
    )
    item = db.get_archive_thread(10, 30, -100999)
    assert item["message_thread_id"] == 777
    assert db.archive_thread_summary()["total"] == 1


def test_cached_messages_for_archive_and_peer_hint(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    db.upsert_message(
        {
            "chat_id": 100,
            "message_id": 1,
            "user_id": 200,
            "username": "peer",
            "text": None,
            "caption": None,
            "media_type": None,
            "file_id": None,
            "file_path": None,
            "raw_json": "",
        }
    )
    db.upsert_message(
        {
            "chat_id": 100,
            "message_id": 2,
            "user_id": 999,
            "username": "owner",
            "text": None,
            "caption": None,
            "media_type": None,
            "file_id": None,
            "file_path": None,
            "raw_json": "",
        }
    )
    assert len(db.cached_messages_for_archive()) == 2
    assert db.latest_peer_for_chat(100, [999])["username"] == "peer"
