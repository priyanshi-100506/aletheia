import asyncio
import logging
import os
import re
import subprocess
import tempfile
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


def _canonical_repo(repo: str) -> str:
    """Normalize repository identifiers to the canonical 'owner/repo' form.
    Supports:
        - owner/repo
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        - trailing slashes and .git suffixes
    """
    repo = repo.strip()
    if "://" in repo:
        # URL form
        parsed = urlparse(repo)
        repo = parsed.path
    elif repo.startswith("git@"):
        repo = repo.split(":", 1)[-1]
    repo = repo.lstrip('/')
    repo = repo.removesuffix('.git').strip('/')
    return repo


async def create_pull_request(
    *,
    repo_path: str,
    branch_name: str,
    patch_diff: str,
    pr_title: str,
    pr_body: str,
    incident_repo: str,
    base_sha: str | None = None,
) -> dict:
    """Create a PR after ensuring the Git remote matches the incident repository.
    Steps:
    1. Verify local remote matches incident_repo.
    2. Push the branch (unless in demo mode).
    3. POST to GitHub to create the PR.
    4. GET the PR to verify its existence.
    """
    repository_path = _repository_path(repo_path)
    branch = branch_name if branch_name.startswith("fix/aletheia-") else f"fix/aletheia-{branch_name}"
    if len(patch_diff) > settings.MAX_PATCH_LENGTH:
        raise ValueError("Patch exceeds the maximum allowed size")

    token = os.getenv("GITHUB_TOKEN", settings.GITHUB_TOKEN)
    base_branch = os.getenv("GITHUB_BASE_BRANCH", settings.GITHUB_BASE_BRANCH)

    # Demo mode – simulate without side effects
    if settings.DEMO_MODE or not token:
        logger.info(
            "[GITHUB PR SIMULATION] DEMO MODE — NO REAL PR CREATED (DEMO_MODE=%s, token_present=%s, branch=%s)",
            settings.DEMO_MODE,
            bool(token),
            branch,
        )
        return {
            "pr_url": None,
            "html_url": None,
            "number": None,
            "simulated": True,
            "mode": "DEMO MODE — NO REAL PR CREATED",
        }

    # Verify remote matches the incident repository (canonical form)
    remote_url = await asyncio.to_thread(_git, str(repository_path), "remote", "get-url", "origin")
    remote_canonical = _canonical_repo(remote_url)
    incident_canonical = _canonical_repo(incident_repo)
    if remote_canonical != incident_canonical:
        raise RuntimeError(
            f"Git remote origin ({remote_canonical}) does not match incident repository ({incident_canonical})"
        )
    head_sha = await asyncio.to_thread(_git, str(repository_path), "rev-parse", "HEAD")
    if base_sha and head_sha.lower() != base_sha.lower():
        raise RuntimeError("Target checkout HEAD does not match the incident base SHA")

    api_repo = incident_canonical
    url = f"https://api.github.com/repos/{api_repo}/pulls"
    timeout = httpx.Timeout(15.0, connect=5.0)

    # Check for existing PRs first
    async with httpx.AsyncClient(timeout=timeout) as client:
        existing = await client.get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            params={"head": f"{api_repo.split('/')[-1]}:{branch}", "base": base_branch, "state": "all"},
        )
        if existing.status_code >= 400:
            sanitized = _sanitize_output(existing.text, token)
            raise RuntimeError(f"GitHub API Error {existing.status_code}: {sanitized}")
        if existing.json():
            data = existing.json()[0]
            if (
                _canonical_repo(data.get("base", {}).get("repo", {}).get("full_name", "")) != incident_canonical
                or data.get("head", {}).get("ref") != branch
                or data.get("base", {}).get("ref") != base_branch
            ):
                raise RuntimeError("Existing PR did not match the approved target and branch")
            return {"pr_url": data["html_url"], "url": data["html_url"], "number": data.get("number"), "data": data, "reused": True}

    # Create worktree, apply patch, commit and push
    pushed_commit_sha = ""
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

            # Push – embed token if needed for HTTPS
            auth_remote = remote_url
            if token and "github.com" in remote_url:
                auth_remote = f"https://x-access-token:{token}@github.com/{api_repo}.git"
            await asyncio.to_thread(
                _git, worktree, "push", auth_remote, f"{branch}:{branch}", token=token
            )
            remote_branch_sha = await asyncio.to_thread(
                _git, worktree, "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}", token=token
            )
            pushed_sha = remote_branch_sha.split()[0] if remote_branch_sha else ""
            local_sha = await asyncio.to_thread(_git, worktree, "rev-parse", "HEAD")
            if pushed_sha != local_sha:
                raise RuntimeError("Remote branch SHA does not match the pushed commit")
            pushed_commit_sha = local_sha
        except Exception as exc:
            sanitized = _sanitize_output(str(exc), token)
            raise RuntimeError(sanitized) from None
        finally:
            try:
                await asyncio.to_thread(_git, str(repository_path), "worktree", "remove", "--force", worktree)
            except Exception:
                pass

    # Create PR via GitHub API
    async with httpx.AsyncClient(timeout=timeout) as client:
        commit_response = await client.get(
            f"https://api.github.com/repos/{api_repo}/commits/{pushed_commit_sha}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if commit_response.status_code >= 400 or commit_response.json().get("sha") != pushed_commit_sha:
            raise RuntimeError("GitHub did not verify the pushed commit")
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": pr_title, "body": pr_body, "head": branch, "base": base_branch},
        )
        if response.status_code >= 400:
            sanitized = _sanitize_output(response.text, token)
            raise RuntimeError(f"GitHub API Error {response.status_code}: {sanitized}")
        data = response.json()

    # Verify PR exists via GET
    pr_number = data.get("number")
    if not pr_number:
        raise RuntimeError("GitHub response missing PR number")
    verify_url = f"{url}/{pr_number}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        verify_resp = await client.get(
            verify_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        )
        if verify_resp.status_code >= 400:
            sanitized = _sanitize_output(verify_resp.text, token)
            raise RuntimeError(f"Failed to verify PR {pr_number}: {sanitized}")
        verified_data = verify_resp.json()

    verified_repo = _canonical_repo(verified_data.get("base", {}).get("repo", {}).get("full_name", ""))
    verified_head = verified_data.get("head", {})
    if (
        verified_repo != incident_canonical
        or verified_data.get("number") != pr_number
        or not verified_data.get("html_url")
        or verified_head.get("ref") != branch
        or verified_head.get("sha") != pushed_commit_sha
        or verified_data.get("base", {}).get("ref") != base_branch
        or (base_sha and verified_data.get("base", {}).get("sha", "").lower() != base_sha.lower())
    ):
        raise RuntimeError("GitHub PR verification did not match the approved target and base")

    return {
        "pr_url": verified_data.get("html_url"),
        "url": verified_data.get("html_url"),
        "number": verified_data.get("number"),
        "data": verified_data,
    }
