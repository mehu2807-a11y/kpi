import urllib.request, json, time
t0 = time.time()
r = urllib.request.urlopen('http://localhost:5000/kpis', timeout=30)
d = json.loads(r.read())
elapsed = time.time() - t0
print(f"Elapsed: {elapsed:.2f}s  ({len(d)} KPIs)")
for k in d:
    print(f"  {k['kpi_id']}: method={k.get('forecast_method','?')} status={k['status']} expected={k.get('expected_value')}")
