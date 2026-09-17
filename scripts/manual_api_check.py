"""Manual API smoke check; intentionally not a pytest test module."""
import json
import warnings

from fastapi.testclient import TestClient

from app.main import app

warnings.filterwarnings("ignore", category=DeprecationWarning)
client = TestClient(app)


def check_health() -> None:
    res = client.get("/health")
    print("Health Status:", res.status_code, res.json())


def check_patch_endpoint() -> None:
    payload = {
        "error_log": "ZeroDivisionError: float division by zero in calculate_transaction_fee at discount_tier / discount_tier"
    }
    res = client.post("/api/v1/patch/generate", json=payload)
    print("HTTP Status:", res.status_code)
    print(json.dumps(res.json(), indent=2))


if __name__ == "__main__":
    check_health()
    check_patch_endpoint()
