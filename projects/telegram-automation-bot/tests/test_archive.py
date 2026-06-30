from types import SimpleNamespace

from services.archive import (
    archive_card,
    archive_message_link,
    archive_thread_title,
    cached_archive_card,
    deleted_card,
    dialog_identity,
    media_label,
)


def test_archive_message_link_private_channel():
    assert archive_message_link(-1004397482368, 55) == "https://t.me/c/4397482368/55"


def test_archive_message_link_forum_topic():
    assert archive_message_link(-1004397482368, 55, 777) == "https://t.me/c/4397482368/777/55"


def test_deleted_card_with_mapping_has_link():
    text = deleted_card(
        -1001,
        22,
        {
            "source_user_id": 123,
            "username": "tester",
            "display_name": "Tester",
            "media_type": "video_note",
            "archive_chat_id": -1004397482368,
            "archive_message_id": 55,
        },
    )
    assert "🗑" in text
    assert "@tester" in text
    assert "кружок" in text
    assert "https://t.me/c/4397482368/55" in text


def test_deleted_card_without_mapping_is_clear():
    text = deleted_card(1, 2, None)
    assert "Копии нет" in text


def test_media_label():
    assert media_label("voice") == "голосовое"
    assert media_label("unknown") == "текст"
    assert media_label("unknown_media") == "медиа"


def test_archive_thread_title_uses_peer_and_owner():
    message = SimpleNamespace(
        chat=SimpleNamespace(id=100),
        from_user=SimpleNamespace(id=200, username="tester", first_name="Test", last_name=None),
    )
    identity = dialog_identity(message, owner_user_id=999, owner_label="@me")
    assert archive_thread_title(message, identity) == "@tester - @me"


def test_dialog_identity_owner_reply_uses_chat_as_peer():
    incoming = SimpleNamespace(
        chat=SimpleNamespace(id=6130557095, username="timkayy", title=None),
        from_user=SimpleNamespace(id=6130557095, username="timkayy", first_name="Peer", last_name=None),
    )
    outgoing = SimpleNamespace(
        chat=SimpleNamespace(id=6130557095, username="timkayy", title=None),
        from_user=SimpleNamespace(id=994582601, username="Enstarboy", first_name="TimKa", last_name=None),
    )
    incoming_identity = dialog_identity(incoming, owner_user_id=994582601, owner_label="@Enstarboy")
    outgoing_identity = dialog_identity(outgoing, owner_user_id=994582601, owner_label="@Enstarboy")
    assert incoming_identity.peer_user_id == outgoing_identity.peer_user_id == 6130557095
    assert archive_thread_title(outgoing, outgoing_identity) == "@timkayy - @Enstarboy"


def test_archive_card_is_clean():
    message = SimpleNamespace(
        chat=SimpleNamespace(id=6130557095),
        message_id=286258,
        from_user=SimpleNamespace(id=994582601, username="Enstarboy", first_name="TimKa", last_name=None),
        text="окак",
        caption=None,
    )
    text = archive_card(message, "text")
    assert "📩" in text
    assert "От" in text
    assert "source chat" not in text
    assert "message_id" in text


def test_cached_archive_card_explains_missing_old_content():
    text = cached_archive_card({"message_id": 10, "user_id": 20, "username": "peer", "text": None, "caption": None}, "unknown_media")
    assert "@peer" in text
    assert "локально" in text
