import os
import logging
import subprocess
import asyncio
import tempfile
from urllib.parse import urlparse
from pathlib import Path

import httpx

from app.config import settings
from app.services.git_applier import _repository_path

logger = logging.getLogger("aletheia")


def _git(repo_path: str, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


async def create_pull_request(
    repo_path: str,
    branch_name: str,
    patch_diff: str,
    pr_title: str,
    pr_body: str,
) -> dict:
    repository_path = _repository_path(repo_path)
    branch = branch_name if branch_name.startswith("fix/aletheia-") else f"fix/aletheia-{branch_name}"
    if len(patch_diff) > settings.MAX_PATCH_LENGTH:
        raise ValueError("Patch exceeds the maximum allowed size")
    remote = await asyncio.to_thread(_git, str(repository_path), "remote", "get-url", "origin")
    token = settings.GITHUB_TOKEN
    if not token:
        logger.warning("[GITHUB PR SIMULATION] GITHUB_TOKEN not set. Simulating PR creation for branch %s", branch)
        return {
            "pr_url": f"https://github.com/aletheia-app/repository/pull/{branch_name[:6]}",
            "html_url": f"https://github.com/aletheia-app/repository/pull/{branch_name[:6]}",
            "number": 101,
            "simulated": True
        }

    repository = settings.GITHUB_REPOSITORY or remote
    if "://" in repository:
        repository = urlparse(repository).path
    else:
        repository = repository.split(":", 1)[-1]
    repository = repository.strip("/").removesuffix(".git")
    url = f"https://api.github.com/repos/{repository}/pulls"
    timeout = httpx.Timeout(15.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": pr_title, "body": pr_body, "head": branch, "base": settings.GITHUB_BASE_BRANCH},
        )
        response.raise_for_status()
        data = response.json()
    return {"pr_url": data["html_url"], "url": data["html_url"], "number": data.get("number"), "data": data}