"""
Tests for alert ingestion security: rate limiting, HMAC signature,
health endpoint availability.
"""
import hmac
import hashlib

from app.config import settings


def test_health_endpoint(client):
    """Liveness probe must return 200 with status=ok."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_webhook_ingest_returns_202_with_job_id(client):
    """A valid alert payload must be accepted and return a job_id."""
    payload = {"error_log": "Test error trace", "target_file": "transaction_service.py"}
    response = client.post("/api/v1/webhooks/ingest", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"
    assert "job_id" in data
    assert len(data["job_id"]) == 36  # UUID format


def test_webhook_ingest_prometheus_payload(client):
    """Prometheus Alertmanager payload must be normalized and accepted."""
    payload = {
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "HighErrorRate"},
                "annotations": {"description": "Error rate above threshold"},
            }
        ]
    }
    response = client.post("/api/v1/webhooks/ingest", json=payload)
    assert response.status_code == 202


def test_webhook_signature_valid(client, monkeypatch):
    """A correctly signed request must be accepted."""
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "test-secret-key")
    payload_bytes = b'{"error_log": "signed payload"}'
    sig = hmac.new(b"test-secret-key", payload_bytes, hashlib.sha256).hexdigest()

    response = client.post(
        "/api/v1/webhooks/ingest",
        content=payload_bytes,
        headers={"X-Hub-Signature-256": f"sha256={sig}", "Content-Type": "application/json"},
    )
    assert response.status_code == 202


def test_webhook_signature_invalid_returns_401(client, monkeypatch):
    """A tampered or missing signature must be rejected with 401."""
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "test-secret-key")
    payload_bytes = b'{"error_log": "unsigned payload"}'

    response = client.post(
        "/api/v1/webhooks/ingest",
        content=payload_bytes,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_patch_apply_forbidden_when_dry_run_false(client):
    """Direct live mutation via /patch/apply must return 403 Forbidden."""
    payload = {
        "repo_root": ".",
        "unified_diff": "--- a/file.py\n+++ b/file.py\n@@ -1 +1 @@\n-old\n+new",
        "dry_run": False,
    }
    response = client.post("/api/v1/patch/apply", json=payload)
    assert response.status_code == 403
    assert "Direct live repository mutation is disabled" in response.json()["detail"]


def test_safe_read_target_file_blocks_path_traversal():
    """Path traversal outside repo root must be blocked and return None."""
    from app.services.patcher import _safe_read_target_file

    assert _safe_read_target_file("../../etc/passwd") is None
    assert _safe_read_target_file("..\\..\\windows\\system32\\drivers\\etc\\hosts") is None
    assert _safe_read_target_file("/etc/shadow") is None


def test_safe_read_target_file_blocks_sensitive_files():
    """Sensitive files (.env, keys) must be blocked from reading into prompt."""
    from app.services.patcher import _safe_read_target_file

    assert _safe_read_target_file(".env") is None
    assert _safe_read_target_file(".env.production") is None
    assert _safe_read_target_file("id_rsa") is None
    assert _safe_read_target_file("server.key") is None


def test_sanitize_output_redacts_credentials():
    """PATs and tokens embedded in URLs or logs must be redacted."""
    from app.services.github_service import _sanitize_output

    raw_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyz"
    url_with_token = f"https://x-access-token:{raw_token}@github.com/org/repo.git"
    sanitized = _sanitize_output(f"Failed to push to {url_with_token}", token=raw_token)

    assert raw_token not in sanitized
    assert "[REDACTED" in sanitized


def test_patch_rejects_unexpected_target_file():
    from app.services.git_applier import PatchApplicationError, _validate_diff_paths

    diff = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"
    try:
        _validate_diff_paths(diff, allowed_target="authentication.py")
    except PatchApplicationError as exc:
        assert "outside" in str(exc)
    else:
        raise AssertionError("unexpected patch target was accepted")
