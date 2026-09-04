import asyncio
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.git_applier import _repository_path

logger = logging.getLogger("aletheia")


def _sanitize_output(text: str, token: str | None = None) -> str:
    """Scrub sensitive credentials, tokens, and URLs from error text."""
    if not text:
        return ""
    if token:
        text = text.replace(token, "[REDACTED_TOKEN]")
    # Redact access tokens in URLs
    text = re.sub(r"https?://x-access-token:[^@]+@", "https://x-access-token:[REDACTED]@", text)
    text = re.sub(r"https?://[^@\s]+:[^@\s]+@", "https://[REDACTED]@", text)
    text = re.sub(r"ghp_[A-Za-z0-9_]+", "[REDACTED_GH_TOKEN]", text)
    text = re.sub(r"github_pat_[A-Za-z0-9_]+", "[REDACTED_GH_PAT]", text)
    return text


def _git(repo_path: str, *args: str, token: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_path, capture_output=True, text=True, check=False, timeout=30
    )
    if result.returncode:
        sanitized_err = _sanitize_output(result.stderr.strip() or f"git {' '.join(args)} failed", token)
        raise RuntimeError(sanitized_err)
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

    token = os.getenv("GITHUB_TOKEN", settings.GITHUB_TOKEN)
    target_repo = os.getenv("GITHUB_REPOSITORY", settings.GITHUB_REPOSITORY)
    base_branch = os.getenv("GITHUB_BASE_BRANCH", settings.GITHUB_BASE_BRANCH)

    if not token:
        logger.warning(
            "[GITHUB PR SIMULATION] GITHUB_TOKEN not set. Simulating PR creation for branch %s",
            branch,
        )
        return {
            "pr_url": f"https://github.com/aletheia-app/repository/pull/{branch_name[:6]}",
            "html_url": f"https://github.com/aletheia-app/repository/pull/{branch_name[:6]}",
            "number": 101,
            "simulated": True,
        }

    remote = await asyncio.to_thread(_git, str(repository_path), "remote", "get-url", "origin")

    # 1. Create worktree, apply patch, commit & push branch to remote
    with tempfile.TemporaryDirectory(prefix="aletheia-worktree-") as worktree:
        await asyncio.to_thread(_git, str(repository_path), "worktree", "add", "--detach", worktree, "HEAD")
        try:
            await asyncio.to_thread(_git, worktree, "checkout", "-b", branch)
            apply_res = await asyncio.to_thread(
                subprocess.run,
                ["git", "apply", "-"],
                input=patch_diff,
                cwd=worktree,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if apply_res.returncode != 0:
                raise RuntimeError(f"Patch application failed in worktree: {apply_res.stderr.strip()}")

            await asyncio.to_thread(_git, worktree, "add", "-A")
            await asyncio.to_thread(
                _git, worktree, "commit", "-m", f"fix(autofix): resolve incident {branch_name[:8]}"
            )

            # Embed PAT into push URL if pushing over HTTPS
            auth_remote = remote
            if token and "github.com" in remote:
                auth_remote = f"https://x-access-token:{token}@github.com/{target_repo or 'priyanshi-100506/aletheia'}.git"

            await asyncio.to_thread(
                _git, worktree, "push", auth_remote, f"{branch}:{branch}", token=token
            )
        except Exception as exc:
            sanitized_msg = _sanitize_output(str(exc), token)
            raise RuntimeError(sanitized_msg) from None
        finally:
            try:
                await asyncio.to_thread(_git, str(repository_path), "worktree", "remove", "--force", worktree)
            except Exception:
                pass

    repository = target_repo or remote
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
            json={"title": pr_title, "body": pr_body, "head": branch, "base": base_branch},
        )
        if response.status_code >= 400:
            sanitized_resp = _sanitize_output(response.text, token)
            raise RuntimeError(f"GitHub API Error {response.status_code}: {sanitized_resp}")
        data = response.json()
    return {"pr_url": data["html_url"], "url": data["html_url"], "number": data.get("number"), "data": data}