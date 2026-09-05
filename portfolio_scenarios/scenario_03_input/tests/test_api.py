import pytest
from api import parse_age


def test_negative_age_is_rejected():
    with pytest.raises(ValueError, match="age"):
        parse_age({"age": -1})


def test_valid_age_is_returned():
    assert parse_age({"age": 42}) == 42
