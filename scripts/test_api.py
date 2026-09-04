import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    res = client.get("/health")
    print("Health Status:", res.status_code, res.json())

def test_patch_endpoint():
    payload = {
        "error_log": "ZeroDivisionError: float division by zero in calculate_transaction_fee at discount_tier / discount_tier"
    }
    print("\nSending POST request to /api/v1/patch/generate...")
    res = client.post("/api/v1/patch/generate", json=payload)
    print("HTTP Status:", res.status_code)
    print("Response Payload:")
    import json
    print(json.dumps(res.json(), indent=2))

if __name__ == "__main__":
    test_health()
    test_patch_endpoint()
