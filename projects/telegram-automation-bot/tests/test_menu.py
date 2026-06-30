from pathlib import Path

from bot.menu import MENU_CALLBACKS, main_menu_text, page_for_callback
from services.platform_checks import PlatformReport
from storage.database import Database


class Item:
    name = "python"
    ok = True
    detail = "ok"


def test_menu_text_has_core_sections(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    report = PlatformReport(os_name="Darwin", python_version="3.11", items=[Item()])
    text = main_menu_text(db, report)
    assert "Chat Automation Control" in text
    assert "Business" in text
    assert "Сообщения" in text


def test_menu_callbacks_have_pages(tmp_path: Path):
    db = Database(tmp_path / "bot.sqlite3")
    db.initialize()
    report = PlatformReport(os_name="Darwin", python_version="3.11", items=[Item()])
    for callback_data in MENU_CALLBACKS:
        assert page_for_callback(callback_data, db, report)

