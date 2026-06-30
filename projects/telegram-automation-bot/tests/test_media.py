from services.media import safe_filename
from app.config import _parse_optional_int


def test_safe_filename():
    assert safe_filename("a/b:c d") == "a_b_c_d"
    assert safe_filename("???") == "file"


def test_parse_optional_int_accepts_braces():
    assert _parse_optional_int("{-1004397482368}") == -1004397482368
    assert _parse_optional_int("") is None
