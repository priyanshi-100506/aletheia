import pytest
import hmac
import hashlib
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_webhook_ingest_rate_limit_and_flow():
    payload = {"error_log": "Test error trace", "target_file": "transaction_service.py"}
    response = client.post("/api/v1/webhooks/ingest", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "processing"
    assert "job_id" in data

def test_webhook_signature_verification(monkeypatch):
    monkeypatch.setattr(settings, "WEBHOOK_SECRET", "super-secret-key")
    payload_bytes = b'{"error_log": "Secret payload"}'
    mac = hmac.new(b"super-secret-key", payload_bytes, hashlib.sha256).hexdigest()

    headers = {"X-Hub-Signature-256": f"sha256={mac}", "Content-Type": "application/json"}
    
    # Valid signature
    res = client.post("/api/v1/webhooks/ingest", content=payload_bytes, headers=headers)
    assert res.status_code == 202

    # Invalid signature
    bad_headers = {"X-Hub-Signature-256": "sha256=invalid", "Content-Type": "application/json"}
    res_bad = client.post("/api/v1/webhooks/ingest", content=payload_bytes, headers=bad_headers)
    assert res_bad.status_code == 401
