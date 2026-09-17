"""
Deterministic scenario mappings and configuration constants for ALETHEIA demo mode.
"""

SCENARIO_TO_TEST: dict[str, str] = {
    "scenario_1": "tests/test_users.py::test_display_name_none",
    "scenario_2": "tests/test_external_api.py::test_external_api_error",
    "scenario_3": "tests/test_validation.py::test_api_validation",
    "scenario_4": "tests/test_reports.py::test_db_query_logic",
    "scenario_5": "tests/test_regression.py::test_regression",
}

SCENARIO_TARGET_FILES: dict[str, str] = {
    "scenario_1": "incident_demo/services/users.py",
    "scenario_2": "incident_demo/services/external_api.py",
    "scenario_3": "incident_demo/schemas.py",
    "scenario_4": "incident_demo/services/reports.py",
    "scenario_5": "incident_demo/services/utils.py",
}
