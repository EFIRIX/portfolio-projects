from services.text_tools import contains_profanity, feature_key, make_angry, make_kind, switch_layout


def test_switch_layout_en_to_ru():
    assert switch_layout("ghbdtn") == "привет"


def test_switch_layout_ru_to_en():
    assert switch_layout("руддщ") == "hello"


def test_profanity_filter():
    assert contains_profanity("привет ты хуй")
    assert not contains_profanity("привет как дела")


def test_modes_return_text():
    assert "дружелюбно" in make_kind("Привет")
    assert "резко" in make_angry("Привет")


def test_feature_key():
    assert feature_key(".Media ") == "media"

