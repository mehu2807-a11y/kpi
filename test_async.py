import requests
import time

print("Testing Async /analyze")

# 1. Post to analyze
payload = {
    "test_case": "easy",
    "backend": "mock"
}
res = requests.post("http://localhost:5000/analyze", json=payload)
if res.status_code != 202:
    print(f"FAILED: Expected 202, got {res.status_code}")
    print(res.text)
    exit(1)

data = res.json()
print("POST returned:", data)
job_id = data.get("job_id")

if not job_id:
    print("FAILED: No job_id returned")
    exit(1)

# 2. Poll for status
print(f"Polling job {job_id}...")
start = time.time()
while True:
    time.sleep(1)
    status_res = requests.get(f"http://localhost:5000/analyze/status/{job_id}")
    status_data = status_res.json()
    print(f"Elapsed {int(time.time() - start)}s:", status_data['status'])
    
    if status_data['status'] == 'done':
        print("SUCCESS! Job completed.")
        assert 'result' in status_data
        break
    elif status_data['status'] == 'error':
        print("JOB FAILED:", status_data.get('error'))
        exit(1)
        
    if time.time() - start > 60:
        print("FAILED: Timed out waiting for job")
        exit(1)
