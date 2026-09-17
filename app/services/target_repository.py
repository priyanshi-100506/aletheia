"""Ephemeral, identity-checked checkouts for incident target repositories."""
import asyncio
import shutil
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.services.github_service import _canonical_repo


def validate_incident_repository(repository: str) -> str:
    canonical = _canonical_repo(repository).lower()
    allowed = {_canonical_repo(item).lower() for item in settings.ALLOWED_REPOS}
    if canonical not in allowed:
        raise ValueError("Incident repository is not in the configured allowlist")
    return canonical


def _run(*args: str, cwd: str | None = None) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")


@asynccontextmanager
async def checked_out_target(repository: str, base_sha: str | None):
    """Clone only the incident repository and pin it to its requested base SHA.

    A checkout is deliberately short-lived: it cannot be confused with the
    ALETHEIA application checkout and it is never reused for a later incident.
    """
    canonical = validate_incident_repository(repository)
    workspace = tempfile.mkdtemp(prefix="aletheia-target-")
    try:
        remote = f"https://github.com/{canonical}.git"
        await asyncio.to_thread(_run, "clone", "--no-checkout", remote, workspace)
        await asyncio.to_thread(_run, "checkout", "--detach", base_sha or "HEAD", cwd=workspace)
        actual_remote = await asyncio.to_thread(
            subprocess.check_output, ["git", "remote", "get-url", "origin"], cwd=workspace, text=True
        )
        if _canonical_repo(actual_remote) != canonical:
            raise RuntimeError("Target checkout remote does not match incident repository")
        actual_sha = await asyncio.to_thread(
            subprocess.check_output, ["git", "rev-parse", "HEAD"], cwd=workspace, text=True
        )
        if base_sha and actual_sha.strip().lower() != base_sha.lower():
            raise RuntimeError("Target checkout does not match the incident base SHA")
        yield Path(workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
