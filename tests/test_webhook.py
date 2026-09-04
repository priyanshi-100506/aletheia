"""
Unit tests for alert normalization, orchestrator pipeline logic,
and ingest endpoint behaviour.

All external I/O (Gemini API, GitHub, PostgreSQL) is mocked.
Tests use pure in-process function calls via asyncio.run() where possible,
or the session-scoped `client` fixture for endpoint-level tests.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.schemas.patch import PatchResult
from app.schemas.webhook import normalize_alert
from app.models.remediation import PatchStatus, RemediationJob
from app.services import orchestrator


# ── Schema / normalization tests ───────────────────────────────────────────────

def test_normalize_generic_payload():
    """Generic payloads must map directly to (error_log, target_file)."""
    result = normalize_alert({"error_log": "DB connection failed", "target_file": "db.py"})
    assert result.error_log == "DB connection failed"
    assert result.target_file == "db.py"


def test_normalize_prometheus_payload():
    """Prometheus firing alerts must extract description annotation."""
    result = normalize_alert({
        "alerts": [{
            "status": "firing",
            "labels": {"alertname": "service_down"},
            "annotations": {"description": "Service unavailable on port 8080"},
        }]
    })
    assert "Service unavailable" in result.error_log


def test_normalize_datadog_payload():
    """Datadog payloads must fall through to the Datadog normalizer."""
    result = normalize_alert({"message": "CPU spike on worker-3", "alertType": "error"})
    assert "CPU spike" in result.error_log


# ── Orchestrator pipeline unit tests ──────────────────────────────────────────

class _FakeSession:
    """Minimal async DB session mock that records committed statuses."""

    def __init__(self, job: RemediationJob):
        self.job = job
        self.committed_statuses: list[PatchStatus] = []
        self._added: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, _model, _id):
        return self.job

    def add(self, obj):
        self._added.append(obj)

    async def commit(self):
        if hasattr(self.job, "status"):
            self.committed_statuses.append(self.job.status)

    async def rollback(self):
        pass


class _SessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self._session


def _make_patch() -> PatchResult:
    return PatchResult(
        file_path="app.py",
        explanation="Replaced deprecated call",
        bug_description="Null pointer on line 42",
        unified_diff="--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n",
        confidence_score=0.95,
    )


def test_orchestrator_full_pipeline_auto_approve(monkeypatch):
    """Full happy-path pipeline with auto_approve=True must create a PR."""
    job_id = "test-job-001"
    job = RemediationJob(id=job_id, error_log="error", status=PatchStatus.PENDING)
    session = _FakeSession(job)
    patch = _make_patch()

    async def fake_generate(db, error_log, target_file, job_id):
        return patch, job

    async def fake_dry_run(repo_root, unified_diff, dry_run):
        return {"status": "dry_run_passed"}

    async def fake_pr(*args, **kwargs):
        return {"pr_url": "https://github.com/org/repo/pull/99", "number": 99}

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", _SessionFactory(session))
    monkeypatch.setattr(orchestrator, "generate_patch", fake_generate)
    monkeypatch.setattr(orchestrator, "apply_unified_diff", fake_dry_run)
    monkeypatch.setattr(orchestrator, "create_pull_request", fake_pr)

    ctx = {}  # ARQ context (not used in tests)
    result = asyncio.run(
        orchestrator.process_remediation_job(ctx, job_id, "error", "app.py", auto_approve=True)
    )

    assert result["pr_url"].endswith("/pull/99")
    assert PatchStatus.DRY_RUN_PASSED in session.committed_statuses
    assert PatchStatus.PR_CREATED in session.committed_statuses


def test_orchestrator_awaits_approval_when_auto_approve_false(monkeypatch):
    """Pipeline with auto_approve=False must stop at WAIT_FOR_APPROVAL."""
    job_id = "test-job-002"
    job = RemediationJob(id=job_id, error_log="error", status=PatchStatus.PENDING)
    session = _FakeSession(job)
    patch = _make_patch()

    async def fake_generate(db, error_log, target_file, job_id):
        return patch, job

    async def fake_dry_run(repo_root, unified_diff, dry_run):
        return {"status": "dry_run_passed"}

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", _SessionFactory(session))
    monkeypatch.setattr(orchestrator, "generate_patch", fake_generate)
    monkeypatch.setattr(orchestrator, "apply_unified_diff", fake_dry_run)

    ctx = {}
    result = asyncio.run(
        orchestrator.process_remediation_job(ctx, job_id, "error", "app.py", auto_approve=False)
    )

    assert result["status"] == "dry_run_passed"
    assert PatchStatus.WAIT_FOR_APPROVAL in session.committed_statuses


def test_orchestrator_marks_failed_on_generate_error(monkeypatch):
    """A Gemini API failure must mark the job FAILED and return error dict."""
    job_id = "test-job-003"
    job = RemediationJob(id=job_id, error_log="error", status=PatchStatus.PENDING)
    session = _FakeSession(job)

    async def failing_generate(*args, **kwargs):
        raise RuntimeError("Gemini API timeout")

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", _SessionFactory(session))
    monkeypatch.setattr(orchestrator, "generate_patch", failing_generate)

    ctx = {}
    result = asyncio.run(
        orchestrator.process_remediation_job(ctx, job_id, "error", "app.py", auto_approve=True)
    )

    assert result["status"] == "failed"
    assert "Gemini API timeout" in result["error"]
    assert PatchStatus.FAILED in session.committed_statuses


def test_orchestrator_marks_failed_on_dry_run_error(monkeypatch):
    """A dry-run failure must mark the job FAILED and return error dict."""
    job_id = "test-job-004"
    job = RemediationJob(id=job_id, error_log="error", status=PatchStatus.PENDING)
    session = _FakeSession(job)
    patch = _make_patch()

    async def fake_generate(db, error_log, target_file, job_id):
        return patch, job

    async def failing_dry_run(*args, **kwargs):
        raise RuntimeError("patch conflict on line 12")

    monkeypatch.setattr(orchestrator, "AsyncSessionLocal", _SessionFactory(session))
    monkeypatch.setattr(orchestrator, "generate_patch", fake_generate)
    monkeypatch.setattr(orchestrator, "apply_unified_diff", failing_dry_run)

    ctx = {}
    result = asyncio.run(
        orchestrator.process_remediation_job(ctx, job_id, "error", "app.py", auto_approve=True)
    )

    assert result["status"] == "failed"
    assert "conflict" in result["error"]
    assert PatchStatus.FAILED in session.committed_statuses
