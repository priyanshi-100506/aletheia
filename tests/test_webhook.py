import asyncio
from unittest.mock import MagicMock
from fastapi import BackgroundTasks

from app.api.v1.endpoints.webhooks import ingest_alert
from app.models.remediation import PatchStatus, RemediationJob
from app.schemas.patch import PatchResult
from app.schemas.webhook import normalize_alert
from app.services import orchestrator


def test_normalize_generic_and_prometheus_payloads():
	generic = normalize_alert({"error_log": "failed", "target_file": "app.py"})
	prometheus = normalize_alert({
		"alerts": [{
			"status": "firing",
			"labels": {"alertname": "service_down"},
			"annotations": {"description": "service unavailable"},
		}]
	})

	assert generic.error_log == "failed"
	assert generic.target_file == "app.py"
	assert prometheus.error_log == "service unavailable"


def test_ingest_returns_accepted_response_and_queues_job():
	background_tasks = BackgroundTasks()
	fake_request = MagicMock()
	fake_request.client.host = "127.0.0.1"

	async def get_body():
		return b'{"error_log": "failed"}'

	fake_request.body = get_body

	response = asyncio.run(ingest_alert(fake_request, background_tasks, {"error_log": "failed"}))

	assert response["status"] == "processing"
	assert response["job_id"]
	assert len(background_tasks.tasks) == 1
	assert background_tasks.tasks[0].func is orchestrator.process_remediation_job


class FakeSession:
	def __init__(self, job):
		self.job = job
		self.statuses = []

	async def __aenter__(self):
		return self

	async def __aexit__(self, *args):
		return False

	async def get(self, model, job_id):
		return self.job

	def add(self, entity):
		pass

	async def commit(self):
		if hasattr(self.job, 'status'):
			self.statuses.append(self.job.status)

	async def rollback(self):
		pass


class FakeSessionFactory:
	def __init__(self, session):
		self.session = session

	def __call__(self):
		return self.session


def test_orchestrator_runs_pipeline_and_updates_status(monkeypatch):
	job_id = "job-1"
	job = RemediationJob(id=job_id, error_log="failed", status=PatchStatus.PENDING)
	session = FakeSession(job)
	patch = PatchResult(
		file_path="app.py",
		explanation="fixed",
		bug_description="bug",
		unified_diff="diff",
		confidence_score=0.9,
	)
	calls = []

	async def fake_generate(db, error_log, target_file, job_id):
		calls.append("generate")
		return patch, job

	async def fake_apply(repo_path, unified_diff, dry_run):
		calls.append(("apply", dry_run))
		return {"status": "dry_run_passed"}

	async def fake_pr(*args, **kwargs):
		calls.append("pr")
		return {"pr_url": "https://github.com/example/example/pull/1", "html_url": "https://github.com/example/example/pull/1"}

	monkeypatch.setattr(orchestrator, "AsyncSessionLocal", FakeSessionFactory(session))
	monkeypatch.setattr(orchestrator, "generate_patch", fake_generate)
	monkeypatch.setattr(orchestrator, "apply_unified_diff", fake_apply)
	monkeypatch.setattr(orchestrator, "create_pull_request", fake_pr)

	result = asyncio.run(orchestrator.process_remediation_job(job_id, "failed", "app.py", auto_approve=True))

	assert result["pr_url"].endswith("/pull/1")
	assert calls == ["generate", ("apply", True), "pr"]
	assert PatchStatus.DRY_RUN_PASSED in session.statuses
	assert PatchStatus.PR_CREATED in session.statuses


def test_orchestrator_marks_failed_when_dry_run_fails(monkeypatch):
	job_id = "job-2"
	job = RemediationJob(id=job_id, error_log="failed", status=PatchStatus.PENDING)
	session = FakeSession(job)
	patch = PatchResult(
		file_path="app.py",
		explanation="fixed",
		bug_description="bug",
		unified_diff="diff",
		confidence_score=0.9,
	)

	async def fake_generate(db, error_log, target_file, job_id):
		return patch, job

	async def failing_apply(*args, **kwargs):
		raise RuntimeError("conflict")

	monkeypatch.setattr(orchestrator, "AsyncSessionLocal", FakeSessionFactory(session))
	monkeypatch.setattr(orchestrator, "generate_patch", fake_generate)
	monkeypatch.setattr(orchestrator, "apply_unified_diff", failing_apply)

	result = asyncio.run(orchestrator.process_remediation_job(job_id, "failed", "app.py", auto_approve=True, max_retries=0))

	assert result == {"status": "failed", "error": "conflict"}
	assert job.status == PatchStatus.FAILED
	assert job.error_message == "conflict"
