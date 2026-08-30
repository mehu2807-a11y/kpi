"""Pre-warm the Prophet cache for all KPIs from the live database."""
import sys
sys.path.insert(0, 'd:/project')
sys.path.insert(0, 'd:/project/orchestrator')
sys.path.insert(0, 'd:/project/task1')

from kpis_endpoint import _load_metrics_table, KPI_ID_TO_METRIC_NAME
from prophet_forecast import forecast_next
import time

mt = _load_metrics_table()
kpis = ['revenue_total', 'units_sold', 'avg_price', 'marketing_spend', 'inventory_level']

for kpi_id in kpis:
    metric_name = KPI_ID_TO_METRIC_NAME.get(kpi_id, kpi_id)
    product = 'ALL' if kpi_id == 'marketing_spend' else 'Product A'
    s = mt[
        (mt['region'] == 'Region X') &
        (mt['product'] == product) &
        (mt['metric_name'] == metric_name)
    ].sort_values('date')
    if len(s) < 60:
        print(f"  {kpi_id}: only {len(s)} rows, skipping (will use trailing-mean)")
        continue
    t0 = time.time()
    print(f"  Fitting Prophet for {kpi_id} ({len(s)} rows)...", end='', flush=True)
    r = forecast_next(s['date'].tolist(), s['value'].tolist(), use_cache=True)
    elapsed = time.time() - t0
    if r.method == 'prophet':
        print(f" {elapsed:.1f}s -> expected={r.expected:.1f} CI=[{r.lower:.1f},{r.upper:.1f}]")
    else:
        print(f" fallback ({r.method})")

print("Cache warm-up complete. /kpis will now return instantly.")
