import pytest
from ..profile import display_name


def test_missing_user_has_safe_display_name():
    assert display_name(None) == "Unknown user"


def test_name_is_trimmed():
    assert display_name({"name": " Ada "}) == "Ada"
