"""Run the zero-credit deterministic scenario catalog."""
import argparse
from scenarios import SCENARIOS, get_scenario


def render(scenario: dict) -> None:
    result = "PASS" if scenario["expected"] == "PASS" else "SAFE FAILURE"
    pr = "SIMULATED / CREATED" if scenario["allowed"] else "NONE"
    print("=" * 50)
    print(f"ALETHEIA SCENARIO: {scenario['id']}")
    print(f"Incident: {scenario['incident']}")
    print(f"Affected file: {scenario['file']}")
    print(f"Expected: {scenario['root_cause']} -> {scenario['remediation']}")
    print(f"Allowed target: {scenario['allowed_file']}")
    print(f"Actual: deterministic fixture ({scenario['expected']})")
    print(f"Patch: {'accepted' if scenario['allowed'] else 'rejected by policy'}")
    print(f"Validation: {scenario['validation']}")
    print(f"Approval: {'REQUIRED' if scenario['approval'] else 'NOT REACHED'}")
    print(f"PR: {pr}")
    print(f"Result: {result}")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ALETHEIA controlled scenarios")
    parser.add_argument("scenario", nargs="?", help="SC-01 through SC-12")
    parser.add_argument("--all", action="store_true", dest="run_all")
    args = parser.parse_args()
    if not args.run_all and not args.scenario:
        parser.error("provide a scenario ID or --all")
    selected = SCENARIOS if args.run_all else [get_scenario(args.scenario)]
    for scenario in selected:
        render(scenario)


if __name__ == "__main__":
    main()
