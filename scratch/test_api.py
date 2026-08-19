import urllib.request
import json
import sys

def test_insights():
    print("Testing /api/insights...")
    try:
        req = urllib.request.Request("http://127.0.0.1:5000/api/insights")
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read().decode('utf-8'))
            print("Keys returned:", list(data.keys()))
            assert "default_doc_body" in data
            assert "default_email_body" in data
            assert "default_email_subject" in data
            print("default_email_subject:", data.get("default_email_subject"))
            print("Insights endpoint test passed!\n")
    except Exception as e:
        print("Insights endpoint test failed:", e)
        sys.exit(1)

def test_deliver_validation():
    print("Testing /api/deliver validation (both disabled should fail)...")
    payload = {
        "email_subject": "Test subject",
        "run_id": "Groww-2026-W33",
        "deliver_to_doc": False,
        "deliver_to_email": False
    }
    req_data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        "http://127.0.0.1:5000/api/deliver",
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            print("Deliver validation failed: request should have been rejected.")
            sys.exit(1)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        print(f"Success: Deliver rejected with code {e.code}: {body}")
        assert e.code == 400
        print("Deliver validation test passed!\n")
    except Exception as e:
        print("Deliver validation test failed with unexpected error:", e)
        sys.exit(1)

if __name__ == "__main__":
    test_insights()
    test_deliver_validation()
    print("All backend checks passed successfully!")
