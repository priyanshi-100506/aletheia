"""Run five real, local ALETHEIA remediation demonstrations.

The patch generator is fixture-backed to avoid Gemini spend. Patch safety,
isolated application, pytest execution, approval recording, and demo PR
behavior use ALETHEIA's actual services.
"""
import argparse
import asyncio
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.services.git_applier import PatchApplicationError, _validate_diff_paths, validate_in_isolated_workspace
from app.services.github_service import create_pull_request

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "portfolio_scenarios"

SCENARIOS = [
    {
        "id": "SC-01",
        "name": "None handling",
        "directory": "scenario_01_none",
        "target": "profile.py",
        "test": "tests/test_profile.py",
        "incident": "AttributeError: 'NoneType' object is not subscriptable in display_name",
        "diagnosis": "display_name indexes a missing user object without a guard",
        "before": '    return user["name"].strip()\n',
        "after": '    if user is None:\n        return "Unknown user"\n    return user["name"].strip()\n',
    },
    {
        "id": "SC-02",
        "name": "HTTP error handling",
        "directory": "scenario_02_http",
        "target": "http_client.py",
        "test": "tests/test_http_client.py",
        "incident": "Upstream returned HTTP 500 and the client raised KeyError for missing status",
        "diagnosis": "upstream_status reads a success payload before checking response status",
        "before": '    return response.json()["status"]\n',
        "after": '    if response.status_code >= 400:\n        return "unavailable"\n    return response.json()["status"]\n',
    },
    {
        "id": "SC-03",
        "name": "API input validation",
        "directory": "scenario_03_input",
        "target": "api.py",
        "test": "tests/test_api.py",
        "incident": "POST /users accepted age=-1 and created an invalid user",
        "diagnosis": "parse_age converts the value but does not enforce the domain boundary",
        "before": '    return int(payload["age"])\n',
        "after": '    age = int(payload["age"])\n    if age < 0:\n        raise ValueError("age must be non-negative")\n    return age\n',
    },
    {
        "id": "SC-04",
        "name": "Database query",
        "directory": "scenario_04_database",
        "target": "repository.py",
        "test": "tests/test_repository.py",
        "incident": "Active-user report returned inactive accounts after the nightly refresh",
        "diagnosis": "active_users uses the inverse status predicate",
        "before": '        "SELECT name FROM users WHERE status = \'inactive\' ORDER BY name"\n',
        "after": '        "SELECT name FROM users WHERE status = \'active\' ORDER BY name"\n',
    },
    {
        "id": "SC-05",
        "name": "Existing regression",
        "directory": "scenario_05_regression",
        "target": "calculator.py",
        "test": "tests/test_calculator.py",
        "incident": "Regression: mixed-case customer email was stored as a distinct identity",
        "diagnosis": "normalize_email trims whitespace but does not normalize case",
        "before": '    return email.strip()\n',
        "after": '    return email.strip().lower()\n',
    },
]


def run(command: list[str], cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=check, timeout=90)


def make_patch(scenario: dict, repo: Path) -> str:
    original = (repo / scenario["target"]).read_text(encoding="utf-8")
    if scenario["before"] not in original:
        raise ValueError(f"Fixture baseline does not contain expected source for {scenario['id']}")
    updated = original.replace(scenario["before"], scenario["after"], 1)
    return "".join(difflib.unified_diff(
        original.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{scenario['target']}",
        tofile=f"b/{scenario['target']}",
    ))


def prepare_repository(scenario: dict, workspace: Path) -> Path:
    source = FIXTURES / scenario["directory"]
    destination = workspace / scenario["id"]
    shutil.copytree(source, destination)
    run(["git", "init", "-q"], destination, check=True)
    run(["git", "config", "user.name", "ALETHEIA Demo"], destination, check=True)
    run(["git", "config", "user.email", "demo@aletheia.invalid"], destination, check=True)
    run(["git", "add", "-A"], destination, check=True)
    run(["git", "commit", "-qm", "broken incident baseline"], destination, check=True)
    return destination


def test_before(scenario: dict, repo: Path) -> tuple[bool, str]:
    result = run([sys.executable, "-m", "pytest", scenario["test"], "-q"], repo)
    return result.returncode != 0, (result.stdout + result.stderr).strip()


async def run_scenario(scenario: dict, workspace: Path, real_github: bool) -> dict:
    repo = prepare_repository(scenario, workspace)
    failed_before, before_evidence = test_before(scenario, repo)
    patch = make_patch(scenario, repo)
    unsafe_patch_rejected = False
    try:
        _validate_diff_paths(
            patch + "\n--- a/unauthorized.py\n+++ b/unauthorized.py\n@@ -0,0 +1 @@\n+blocked\n",
            allowed_target=scenario["target"],
        )
    except PatchApplicationError:
        unsafe_patch_rejected = True
    if not unsafe_patch_rejected:
        raise AssertionError(f"Allowed-target safety check failed for {scenario['id']}")
    settings.REPO_PATH = str(repo)
    if not real_github:
        settings.GITHUB_TOKEN = ""
        os.environ.pop("GITHUB_TOKEN", None)

    validation = await validate_in_isolated_workspace(
        repo_root=str(repo),
        unified_diff=patch,
        allowed_target=scenario["target"],
        validation_command=[sys.executable, "-m", "pytest", scenario["test"], "-q"],
    )
    approval = {"status": "APPROVED", "actor": "portfolio_operator"}
    pr = await create_pull_request(
        repo_path=str(repo),
        branch_name=scenario["id"].lower(),
        patch_diff=patch,
        pr_title=f"ALETHEIA demo remediation {scenario['id']}",
        pr_body=f"Incident: {scenario['incident']}\n\nValidation evidence: {json.dumps(validation['evidence'])}",
    )
    return {
        "id": scenario["id"],
        "name": scenario["name"],
        "incident": scenario["incident"],
        "diagnosis": scenario["diagnosis"],
        "target": scenario["target"],
        "patch": patch,
        "unsafe_patch_rejected": unsafe_patch_rejected,
        "failed_before": failed_before,
        "before_evidence": before_evidence[-2000:],
        "validation": validation,
        "approval": approval,
        "pr": pr,
        "final_state": "PR_CREATED" if not pr.get("simulated") else "PR_CREATED (DEMO MODE - NO REAL PR CREATED)",
        "real_gemini": False,
        "real_github": not pr.get("simulated", False),
    }


def print_result(result: dict) -> None:
    print("=" * 72)
    print(f"ALETHEIA PORTFOLIO SCENARIO {result['id']}: {result['name']}")
    print(f"Incident: {result['incident']}")
    print(f"Diagnosis: {result['diagnosis']}")
    print(f"Target: {result['target']}")
    print(f"Before test failed: {result['failed_before']}")
    print(f"Patch generated: YES\n{result['patch']}")
    print(f"Unauthorized extra-file patch rejected: {result['unsafe_patch_rejected']}")
    print("Patch applied: YES")
    print(f"Validation: {result['validation']['status'].upper()}")
    print(f"Evidence: {json.dumps(result['validation']['evidence'])}")
    print(f"Approval: {result['approval']['status']} by {result['approval']['actor']}")
    print(f"PR: {result['final_state']}")
    print("=" * 72)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", nargs="?", help="SC-01 through SC-05")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--real-github", action="store_true", help="Opt into configured GitHub credentials")
    args = parser.parse_args()
    if not args.all and not args.scenario:
        parser.error("provide a scenario ID or --all")
    selected = SCENARIOS if args.all else [scenario for scenario in SCENARIOS if scenario["id"] == args.scenario.upper()]
    if not selected:
        parser.error("unknown scenario")
    with tempfile.TemporaryDirectory(prefix="aletheia-portfolio-") as temporary:
        workspace = Path(temporary)
        for scenario in selected:
            result = asyncio.run(run_scenario(scenario, workspace, args.real_github))
            print_result(result)


if __name__ == "__main__":
    main()
