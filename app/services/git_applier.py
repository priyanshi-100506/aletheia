import os
import subprocess
import tempfile
import logging
import asyncio
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


def _validate_diff_paths(diff: str) -> None:
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


def _repository_path(repo_root: str) -> Path:
    allowed = Path(settings.REPO_PATH).resolve()
    candidate = Path(repo_root).resolve()
    if candidate != allowed and not candidate.is_relative_to(allowed):
        raise PatchApplicationError("Repository path is outside the configured checkout")
    if not candidate.is_dir() or not (candidate / ".git").exists():
        raise PatchApplicationError(f"Repository root is not a Git checkout: {repo_root}")
    return candidate

async def apply_unified_diff(
    repo_root: str, 
    unified_diff: str, 
    dry_run: bool = False
) -> dict:
    repo_path = _repository_path(repo_root)

    clean_patch = sanitize_diff(unified_diff)
    if len(clean_patch) > settings.MAX_PATCH_LENGTH:
        raise PatchApplicationError("Patch exceeds the maximum allowed size")
    _validate_diff_paths(clean_patch)

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
