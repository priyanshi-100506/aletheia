import pytest
from app.services.patch_validation import compare_regression_results, parse_failed_tests_from_pytest_output

def test_compare_regression_case_1_expected_remediation():
    # CASE 1 — Expected remediation: Baseline has A, B, C; Post-fix has B, C.
    base_stdout = "FAILED tests/test_1.py::test_a - err\nFAILED tests/test_2.py::test_b - err\nFAILED tests/test_3.py::test_c - err"
    postfix_stdout = "FAILED tests/test_2.py::test_b - err\nFAILED tests/test_3.py::test_c - err"
    
    base_full = {"stdout": base_stdout, "stderr": ""}
    postfix_full = {"stdout": postfix_stdout, "stderr": ""}
    
    res = compare_regression_results(base_full, postfix_full)
    assert res["resolved_failures"] == ["tests/test_1.py::test_a"]
    assert res["new_failures"] == []
    assert res["regression_free"] is True

def test_compare_regression_case_2_new_regression():
    # CASE 2 — New regression: Baseline has A, B; Post-fix has B, C.
    base_stdout = "FAILED tests/test_1.py::test_a - err\nFAILED tests/test_2.py::test_b - err"
    postfix_stdout = "FAILED tests/test_2.py::test_b - err\nFAILED tests/test_3.py::test_c - err"
    
    base_full = {"stdout": base_stdout, "stderr": ""}
    postfix_full = {"stdout": postfix_stdout, "stderr": ""}
    
    res = compare_regression_results(base_full, postfix_full)
    assert res["resolved_failures"] == ["tests/test_1.py::test_a"]
    assert res["new_failures"] == ["tests/test_3.py::test_c"]
    assert res["regression_free"] is False

def test_compare_regression_case_3_no_failures():
    # CASE 3 — No failures in baseline or post-fix
    base_full = {"stdout": "10 passed in 0.1s", "stderr": ""}
    postfix_full = {"stdout": "10 passed in 0.1s", "stderr": ""}
    
    res = compare_regression_results(base_full, postfix_full)
    assert res["resolved_failures"] == []
    assert res["new_failures"] == []
    assert res["regression_free"] is True

def test_compare_regression_case_4_postfix_collection_error():
    # CASE 4 — Post-fix collection error
    base_full = {"stdout": "10 passed in 0.1s", "stderr": ""}
    postfix_full = {"stdout": "Interrupted: 1 error during collection", "stderr": "ImportError: cannot import name 'foo'"}
    
    res = compare_regression_results(base_full, postfix_full)
    assert res["regression_free"] is False
    assert any("COLLECTION_ERROR" in f for f in res["postfix_failed_tests"])

def test_compare_regression_case_5_target_passes_but_another_fails():
    # CASE 5 — Target test passes, but another test newly fails
    base_full = {"stdout": "FAILED tests/test_users.py::test_display_name_none - err", "stderr": ""}
    postfix_full = {"stdout": "FAILED tests/test_other.py::test_unrelated - err", "stderr": ""}
    
    res = compare_regression_results(base_full, postfix_full)
    assert res["resolved_failures"] == ["tests/test_users.py::test_display_name_none"]
    assert res["new_failures"] == ["tests/test_other.py::test_unrelated"]
    assert res["regression_free"] is False
