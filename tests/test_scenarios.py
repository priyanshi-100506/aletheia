from scripts.scenarios import SCENARIOS, get_scenario


def test_scenario_catalog_is_complete_and_zero_credit():
    assert len(SCENARIOS) == 12
    assert {scenario["id"] for scenario in SCENARIOS} == {f"SC-{index:02d}" for index in range(1, 13)}


def test_scenario_catalog_contains_safe_failures():
    failures = [scenario for scenario in SCENARIOS if scenario["expected"] == "SAFE FAILURE"]
    assert len(failures) >= 3
    assert all(not scenario["allowed"] for scenario in failures)


def test_scenario_lookup_accepts_demo_names():
    assert get_scenario("scenario-01")["id"] == "SC-01"
    assert get_scenario("SC-12")["name"] == "Duplicate approval"