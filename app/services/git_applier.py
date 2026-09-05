import os
import subprocess
import tempfile
import logging
import asyncio
import shutil
from pathlib import Path

from app.config import settings

logger = logging.getLogger("aletheia")

class PatchApplicationError(Exception):
    pass

def sanitize_diff(raw_diff: str) -> str:
    cleaned = raw_diff.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines)

    cleaned = cleaned.replace("\r\n", "\n")
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    return cleaned


def _validate_diff_paths(diff: str, allowed_target: str | None = None) -> None:
    seen_paths: set[str] = set()
    for line in diff.splitlines():
        if not (line.startswith("--- ") or line.startswith("+++ ")):
            continue
        path = line[4:].split("\t", 1)[0]
        if path == "/dev/null":
            continue
        path = path[2:] if path[:2] in {"a/", "b/"} else path
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise PatchApplicationError("Patch contains an unsafe file path")
        seen_paths.add(candidate.as_posix())

    if not seen_paths:
        raise PatchApplicationError("Patch does not contain a file header")
    if allowed_target:
        target = Path(allowed_target).as_posix().lstrip("./")
        if seen_paths != {target}:
            raise PatchApplicationError("Patch modifies a file outside the requested target")


def _repository_path(repo_root: str, allow_external: bool = False) -> Path:
    allowed = Path(settings.REPO_PATH).resolve()
    candidate = Path(repo_root).resolve()
    if not allow_external and candidate != allowed and not candidate.is_relative_to(allowed):
        raise PatchApplicationError("Repository path is outside the configured checkout")
    if not candidate.is_dir() or not (candidate / ".git").exists():
        raise PatchApplicationError(f"Repository root is not a Git checkout: {repo_root}")
    return candidate

async def apply_unified_diff(
    repo_root: str, 
    unified_diff: str, 
    dry_run: bool = False,
    allowed_target: str | None = None,
    _allow_external_repo: bool = False,
) -> dict:
    repo_path = _repository_path(repo_root, allow_external=_allow_external_repo)

    clean_patch = sanitize_diff(unified_diff)
    if len(clean_patch) > settings.MAX_PATCH_LENGTH:
        raise PatchApplicationError("Patch exceeds the maximum allowed size")
    _validate_diff_paths(clean_patch, allowed_target=allowed_target)

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".patch", delete=False, newline="\n") as patch_file:
        patch_file.write(clean_patch)
        patch_path = patch_file.name

    try:
        # Command flags: --recount fixes hunk line counts, -3 enables 3-way merge fallback
        base_cmd = [
            "git", "apply",
            "--recount",
            "--ignore-space-change",
            "--ignore-whitespace"
        ]

        check_cmd = base_cmd + ["--check", patch_path]
        check_result = await asyncio.to_thread(
            subprocess.run, check_cmd, cwd=str(repo_path), capture_output=True,
            text=True, timeout=30
        )

        if check_result.returncode != 0:
            logger.warning(f"[GIT PATCH STRICT CHECK FAILED] Retrying with 3-way merge fallback: {check_result.stderr}")
            # Try 3-way fallback check
            check_3way_cmd = base_cmd + ["-3", "--check", patch_path]
            check_3way_res = await asyncio.to_thread(
                subprocess.run, check_3way_cmd, cwd=str(repo_path), capture_output=True,
                text=True, timeout=30
            )
            
            if check_3way_res.returncode != 0:
                raise PatchApplicationError(
                    f"Patch validation check failed: {check_result.stderr.strip()}"
                )

        if dry_run:
            logger.info("[GIT PATCH] Dry-run check passed successfully.")
            return {"status": "dry_run_passed", "detail": "Patch applies cleanly without conflicts."}

        apply_cmd = base_cmd + ["-3", patch_path]
        apply_result = await asyncio.to_thread(
            subprocess.run, apply_cmd, cwd=str(repo_path), capture_output=True,
            text=True, timeout=30
        )

        if apply_result.returncode != 0:
            logger.error(f"[GIT PATCH ERROR] Apply failed: {apply_result.stderr}")
            raise PatchApplicationError(f"Failed to apply patch: {apply_result.stderr.strip()}")

        logger.info("[GIT PATCH] Patch successfully applied to codebase.")
        return {"status": "applied", "detail": "Patch applied successfully."}

    finally:
        if os.path.exists(patch_path):
            os.remove(patch_path)


async def validate_in_isolated_workspace(
    repo_root: str,
    unified_diff: str,
    allowed_target: str | None = None,
    validation_command: list[str] | None = None,
) -> dict:
    """Apply a patch to a temporary checkout and run targeted validation."""
    source_repo = _repository_path(repo_root)
    with tempfile.TemporaryDirectory(prefix="aletheia-validation-") as workspace:
        workspace_path = Path(workspace)
        shutil.copytree(
            source_repo,
            workspace_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git"),
        )
        await asyncio.to_thread(
            subprocess.run,
            ["git", "init", "-q"],
            cwd=str(workspace_path),
            check=True,
            capture_output=True,
            text=True,
        )
        await asyncio.to_thread(
            subprocess.run,
            ["git", "add", "-A"],
            cwd=str(workspace_path),
            check=True,
            capture_output=True,
            text=True,
        )
        await asyncio.to_thread(
            subprocess.run,
            ["git", "-c", "user.name=ALETHEIA", "-c", "user.email=aletheia@example.invalid", "commit", "-qm", "baseline"],
            cwd=str(workspace_path),
            check=True,
            capture_output=True,
            text=True,
        )
        result = await apply_unified_diff(
            str(workspace_path), unified_diff, dry_run=False, allowed_target=allowed_target,
            _allow_external_repo=True,
        )
        evidence: dict[str, str | int] = {}
        if validation_command:
            validation = await asyncio.to_thread(
                subprocess.run,
                validation_command,
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
            evidence = {
                "command": " ".join(validation_command),
                "returncode": validation.returncode,
                "stdout": validation.stdout[-4000:],
                "stderr": validation.stderr[-4000:],
            }
            if validation.returncode:
                raise PatchApplicationError(
                    f"Validation command failed: {validation.stderr.strip() or validation.stdout.strip()}"
                )
        elif allowed_target and allowed_target.endswith(".py"):
            syntax = await asyncio.to_thread(
                subprocess.run,
                [os.fspath(Path(os.sys.executable)), "-m", "py_compile", allowed_target],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if syntax.returncode:
                raise PatchApplicationError(f"Targeted syntax validation failed: {syntax.stderr.strip()}")
            evidence = {"command": f"{os.fspath(Path(os.sys.executable))} -m py_compile {allowed_target}", "returncode": 0}
        return {**result, "status": "validation_passed", "workspace": "temporary", "evidence": evidence}
