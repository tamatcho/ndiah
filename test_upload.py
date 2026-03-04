import requests
import os

token = os.environ.get("FIREBASE_TEST_TOKEN", "") 
print(f"Testing... {len(token)} chars token")

headers = {}
if token:
    headers["Authorization"] = f"Bearer {token}"

def test_health():
    resp = requests.get("http://127.0.0.1:8000/health")
    print("Health:", resp.status_code)

test_health()
