from calculator import normalize_email


# This regression test exists before ALETHEIA generates a patch.
def test_email_normalization_is_case_insensitive():
    assert normalize_email("  Ada@Example.COM ") == "ada@example.com"
