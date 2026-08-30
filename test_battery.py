"""Comprehensive endpoint battery for the upgraded KPI Engine."""
import urllib.request, urllib.error, json, time

BASE = 'http://localhost:5000'

def get(path, timeout=30):
    try:
        r = urllib.request.urlopen(f'{BASE}{path}', timeout=timeout)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read()), e.code
        except: return {'error': str(e)}, e.code
    except Exception as e:
        return {'error': str(e)}, 0

def post(path, payload, timeout=30):
    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(f'{BASE}{path}', data=data,
                                     headers={'Content-Type': 'application/json'})
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try: return json.loads(e.read()), e.code
        except: return {'error': str(e)}, e.code
    except Exception as e:
        return {'error': str(e)}, 0

PASS = 0; FAIL = 0

def check(name, data, status, expect_keys=None, expect_status=200):
    global PASS, FAIL
    ok = status == expect_status and 'error' not in data
    if expect_keys:
        ok = ok and all(k in data for k in expect_keys)
    symbol = '✓' if ok else '✗'
    if ok: PASS += 1
    else: FAIL += 1
    val = str(data)[:120].replace('\n','')
    print(f"  {symbol} [{status}] {name}: {val}")

time.sleep(4)  # wait for server

print("=== CORE ENDPOINTS ===")
d, s = get('/kpis')
check('/kpis', d[0] if isinstance(d, list) else d, s,
      expect_keys=['kpi_id','status','trend_direction','early_warning'])

d, s = get('/kpis/revenue_total/history?days=14')
check('/kpis/history', d, s, expect_keys=['dates','values'])

print("\n=== ANALYTICAL ENDPOINTS ===")
d, s = post('/abstain-check', {
    'story_output': {
        'hypotheses': [{'cause': 'A', 'confidence': 0.35}, {'cause': 'B', 'confidence': 0.33}],
        'telemetry': {'evidence_quality_score': 0.25}
    },
    'series_length': 20, 'kpi_id': 'revenue_total'
})
check('/abstain-check', d, s, expect_keys=['verdict'])

d, s = post('/whatif', {'mode': 'simulate', 'driver': 'avg_price',
    'driver_change_pct': -0.05, 'target_kpi': 'revenue_total',
    'current_kpi_value': 85000})
check('/whatif (simulate)', d, s, expect_keys=['predicted_kpi_change_pct'])

d, s = post('/whatif', {'mode': 'explain', 'driver': 'avg_price',
    'driver_change_pct': 0.15, 'target_kpi': 'revenue_total',
    'observed_delta_pct': -0.20})
check('/whatif (explain)', d, s, expect_keys=['explained_delta_pct'])

d, s = post('/pattern-match', {
    'driver_contributions': {'inventory_level': -0.75, 'units_sold': -0.55,
                             'avg_price': 0.05, 'marketing_spend': 0.02}})
check('/pattern-match', d, s, expect_keys=['matches','summary'])

d, s = get('/decompose/revenue_total?days=60')
check('/decompose', d, s, expect_keys=['trend','seasonal','residual'])

d, s = get('/lineage/revenue_total')
check('/lineage', d, s, expect_keys=['lineage_chain','llm_steps'])

print("\n=== NL QUERY + REPORT ===")
d, s = post('/query', {'query': 'Why is revenue down in Region X this week?', 'backend': 'mock'})
check('/query', d, s, expect_keys=['parsed_kpi','parsed_region'])

d, s = get('/report/revenue_total')
check('/report (HTML)', {'ok': True}, s, expect_status=200)

print("\n=== PERSISTENCE ===")
d, s = post('/feedback', {'feedback_type': 'detection_accuracy', 'value': 5,
    'comments': 'Great detection', 'anomaly_id': 'evt_test', 'persona': 'ANALYST',
    'provider_role': 'analyst'})
check('/feedback POST', d, s, expect_keys=['status'])

d, s = get('/feedback/history')
check('/feedback/history', d, s, expect_keys=['records'])

print("\n=== KPI DEFINITION ===")
d, s = post('/kpi/define', {'kpi_id': 'gross_margin', 'name': 'Gross Margin',
    'formula': '(revenue - cogs) / revenue', 'threshold_warning': 0.05,
    'threshold_critical': 0.15, 'business_owner': 'CFO', 'technical_owner': 'Finance Team'})
check('/kpi/define', d, s, expect_keys=['kpi_id'])

print("\n=== WEBHOOK ===")
d, s = post('/webhook/configure', {'url': ''})  # disable
check('/webhook/configure', d, s, expect_keys=['configured'])

print(f"\n{'='*50}")
print(f"RESULT: {PASS} passed, {FAIL} failed out of {PASS+FAIL} tests")
