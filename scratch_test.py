"""Quick endpoint validation script."""
import urllib.request
import urllib.error
import json

BASE = 'http://localhost:5000'

def get(path):
    try:
        r = urllib.request.urlopen(f'{BASE}{path}', timeout=30)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as e:
        return {'error': str(e)}, 0

def post(path, payload):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f'{BASE}{path}', data=data,
                                      headers={'Content-Type': 'application/json'})
        r = urllib.request.urlopen(req, timeout=60)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return json.loads(e.read()), e.code
    except Exception as e:
        return {'error': str(e)}, 0

# 1. /kpis
print('=== GET /kpis ===')
data, status = get('/kpis')
print(f'Status: {status}, KPIs: {len(data)}')
for kpi in data:
    print(f"  {kpi['kpi_id']}: status={kpi.get('status')} trend={kpi.get('trend_direction')} early_warning={kpi.get('early_warning')}")

# 2. /kpis/revenue_total/history
print('\n=== GET /kpis/revenue_total/history ===')
data, status = get('/kpis/revenue_total/history?days=14')
print(f'Status: {status}')
if 'dates' in data:
    print(f"  dates: {data['dates'][:3]}... ({len(data['dates'])} points)")
    print(f"  values: {[round(v,2) for v in data['values'][:3]]}...")
else:
    print(f"  Response: {data}")

# 3. POST /feedback
print('\n=== POST /feedback ===')
data, status = post('/feedback', {
    'feedback_type': 'detection_accuracy',
    'value': 4,
    'comments': 'Good detection on revenue anomaly',
    'anomaly_id': 'evt_00001',
    'persona': 'ANALYST',
    'provider_role': 'analyst'
})
print(f'Status: {status}, Response: {data}')

# 4. GET /feedback/history
print('\n=== GET /feedback/history ===')
data, status = get('/feedback/history')
print(f'Status: {status}, Records: {data.get("total", "?")}')

# 5. POST /analyze with mock backend (fast)
print('\n=== POST /analyze (mock, easy) ===')
data, status = post('/analyze', {'test_case': 'easy', 'backend': 'mock'})
print(f'Status: {status}')
if 'original_story' in data:
    s = data['original_story']
    print(f"  headline: {s['headline'][:70]}...")
    print(f"  confidence: {s['overall_confidence']}, escalate: {s['escalate_flag']}")
    print(f"  telemetry: {data['telemetry']}")
else:
    print(f"  Response keys: {list(data.keys())}")

print('\n=== ALL TESTS DONE ===')
