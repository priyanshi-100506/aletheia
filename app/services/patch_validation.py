import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.git_applier import apply_unified_diff, PatchApplicationError

logger = logging.getLogger("aletheia")


def parse_failed_tests_from_pytest_output(stdout: str, stderr: str) -> set[str]:
    """
    Extract failed test node IDs/names or collection error identifiers from pytest output.
    """
    failed = set()
    combined = (stdout or "") + "\n" + (stderr or "")
    
    # 1. Match FAILED lines: FAILED tests/test_users.py::test_display_name_none - AttributeError...
    for line in combined.splitlines():
        line_str = line.strip()
        if line_str.startswith("FAILED "):
            parts = line_str.split()
            if len(parts) >= 2:
                node_id = parts[1]
                failed.add(node_id)
        # 2. Match ERROR lines (collection/import errors): ERROR portfolio_scenarios/...
        elif line_str.startswith("ERROR "):
            parts = line_str.split()
            if len(parts) >= 2:
                node_id = parts[1]
                failed.add(f"COLLECTION_ERROR::{node_id}")

    # 3. Interrupted / Collection Failure fallback
    if "Interrupted:" in combined or "errors during collection" in combined or "ERRORS" in combined:
        if not any(f.startswith("COLLECTION_ERROR::") for f in failed):
            failed.add("COLLECTION_ERROR::pytest_collection_failed")

    return failed


def compare_regression_results(base_full: dict[str, Any], postfix_full: dict[str, Any]) -> dict[str, Any]:
    """
    Compare baseline full-suite vs post-fix full-suite test results.
    Identifies baseline failed tests, post-fix failed tests, resolved failures, and new failures.
    """
    # Check for collection / execution errors in post-fix
    postfix_stdout = postfix_full.get("stdout", "")
    postfix_stderr = postfix_full.get("stderr", "")
    postfix_has_collection_error = (
        "Interrupted: " in (postfix_stdout + postfix_stderr)
        or "errors during collection" in (postfix_stdout + postfix_stderr)
        or "ERRORS" in (postfix_stdout + postfix_stderr)
    )

    baseline_failed = parse_failed_tests_from_pytest_output(base_full.get("stdout", ""), base_full.get("stderr", ""))
    postfix_failed = parse_failed_tests_from_pytest_output(postfix_stdout, postfix_stderr)

    resolved_failures = baseline_failed - postfix_failed
    new_failures = postfix_failed - baseline_failed

    regression_free = (len(new_failures) == 0) and not postfix_has_collection_error

    return {
        "baseline_failed_tests": sorted(list(baseline_failed)),
        "postfix_failed_tests": sorted(list(postfix_failed)),
        "resolved_failures": sorted(list(resolved_failures)),
        "new_failures": sorted(list(new_failures)),
        "postfix_has_collection_error": postfix_has_collection_error,
        "regression_free": regression_free,
    }


def _run_pytest_in_dir(workdir: Path, test_target: str | None = None) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if test_target:
        cmd.append(test_target)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(workdir)

    res = subprocess.run(
        cmd,
        cwd=str(workdir),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return {
        "command": " ".join(cmd),
        "returncode": res.returncode,
        "passed": res.returncode == 0,
        "stdout": res.stdout[-4000:] if res.stdout else "",
        "stderr": res.stderr[-4000:] if res.stderr else "",
    }


async def run_isolated_validation_pipeline(
    repo_source: str,
    unified_diff: str,
    target_test: str,
    target_file: str | None = None,
) -> dict[str, Any]:
    src_path = Path(repo_source).resolve()
    if not src_path.exists():
        raise FileNotFoundError(f"Source repository path does not exist: {repo_source}")

    with tempfile.TemporaryDirectory(prefix="aletheia-pipeline-") as temp_dir:
        workdir = Path(temp_dir)
        shutil.copytree(
            src_path,
            workdir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "*.pyc"),
        )

        # Baseline git repository inside temp dir
        await asyncio.to_thread(subprocess.run, ["git", "init", "-q"], cwd=str(workdir), check=True)
        await asyncio.to_thread(subprocess.run, ["git", "add", "-A"], cwd=str(workdir), check=True)
        await asyncio.to_thread(
            subprocess.run,
            ["git", "-c", "user.name=ALETHEIA", "-c", "user.email=aletheia@example.com", "commit", "-qm", "baseline"],
            cwd=str(workdir),
            check=True,
        )

        # 1. Baseline Target Test
        logger.info("[VALIDATION] Running baseline target test: %s", target_test)
        base_target = await asyncio.to_thread(_run_pytest_in_dir, workdir, target_test)

        # 2. Baseline Full Test Suite (for regression comparison)
        logger.info("[VALIDATION] Running baseline full test suite")
        base_full = await asyncio.to_thread(_run_pytest_in_dir, workdir, None)

        # 3. Apply Patch
        logger.info("[VALIDATION] Applying patch in isolated workspace")
        apply_res = await apply_unified_diff(
            str(workdir),
            unified_diff,
            dry_run=False,
            allowed_target=target_file,
            _allow_external_repo=True,
        )

        # 4. Post-fix Target Test
        logger.info("[VALIDATION] Running post-fix target test: %s", target_test)
        postfix_target = await asyncio.to_thread(_run_pytest_in_dir, workdir, target_test)

        if not postfix_target["passed"]:
            raise PatchApplicationError(
                f"Target test '{target_test}' failed after applying patch:\n{postfix_target['stdout']}\n{postfix_target['stderr']}"
            )

        # 5. Post-fix Full Test Suite (Regression Evidence)
        logger.info("[VALIDATION] Running post-fix full test suite")
        postfix_full = await asyncio.to_thread(_run_pytest_in_dir, workdir, None)

        # 6. Compare Baseline vs Post-fix Full Suite for Regressions
        comparison = compare_regression_results(base_full, postfix_full)

        passed = (
            postfix_target["passed"]
            and comparison["regression_free"]
        )

        if not passed:
            logger.warning("[VALIDATION] Validation failed regression gate: %s", comparison)
            raise PatchApplicationError(
                f"Patch validation failed due to regression or collection errors. New failures: {comparison['new_failures']}"
            )

        evidence = {
            "target_test": target_test,
            "target_file": target_file,
            "apply_result": apply_res,
            "baseline_target": base_target,
            "postfix_target": postfix_target,
            "baseline_full": base_full,
            "postfix_full": postfix_full,
            "baseline_failed_tests": comparison["baseline_failed_tests"],
            "postfix_failed_tests": comparison["postfix_failed_tests"],
            "resolved_failures": comparison["resolved_failures"],
            "new_failures": comparison["new_failures"],
            "regression_free": comparison["regression_free"],
            "passed": passed,
        }

        return {
            "status": "validation_passed" if passed else "validation_failed",
            "evidence": evidence,
            "baseline_target_result": json.dumps(base_target),
            "postfix_target_result": json.dumps(postfix_target),
            "baseline_full_result": json.dumps(base_full),
            "postfix_full_result": json.dumps(postfix_full),
            "evidence_json": json.dumps(evidence),
        }
