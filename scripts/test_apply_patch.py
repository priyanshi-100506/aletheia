from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_generate_and_apply():
    payload = {
        "error_log": "ZeroDivisionError: float division by zero in calculate_transaction_fee at discount_tier / discount_tier",
        "target_file": "transaction_service.py"
    }
    gen_res = client.post("/api/v1/patch/generate", json=payload)
    assert gen_res.status_code == 200, f"Generate failed: {gen_res.text}"
    res_data = gen_res.json()
    
    job_id = res_data["job_id"]
    diff = res_data["patch"]["unified_diff"]
    print(f"Generated Patch Job ID: {job_id}")
    print("--- Unified Diff ---")
    print(diff)
    print("--------------------")

    apply_payload = {
        "job_id": job_id,
        "unified_diff": diff,
        "repo_root": ".",
        "dry_run": True
    }
    apply_res = client.post("/api/v1/patch/apply", json=apply_payload)
    print("Dry-run Result Status Code:", apply_res.status_code)
    print("Dry-run Response:", apply_res.json())
    assert apply_res.status_code == 200, f"Apply failed: {apply_res.text}"

if __name__ == "__main__":
    test_generate_and_apply()
