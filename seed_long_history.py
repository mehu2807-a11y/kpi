"""
seed_long_history.py -- Seeds bi_pipeline.db with 2-year synthetic history
so that Prophet activates on the live /kpis endpoint.

Run once: python -X utf8 seed_long_history.py
"""
import sys
sys.path.insert(0, 'd:/project/task3')
sys.path.insert(0, 'd:/project/task1')
sys.path.insert(0, 'd:/project/orchestrator')

from synthetic_data import generate_long_history
from pathlib import Path
import sqlite3

DB_PATH = Path('d:/project/task1/bi_pipeline.db')

print("Generating 2-year synthetic history...")
df_raw = generate_long_history(n_days=730)
print(f"  Generated: {len(df_raw)} rows, cols={list(df_raw.columns)}")
print(f"  Date range: {df_raw['date'].min()} to {df_raw['date'].max()}")

# synthetic_data cols: date, region, metric, actual_value, ...
# metrics_table cols:  date, region, product, metric_name, value
# Map the gate-format synthetic data to the storage format
df = df_raw.copy()
df = df.rename(columns={'metric': 'metric_name', 'actual_value': 'value'})

# Map metric names: synthetic uses traffic/units_sold/revenue/avg_order_value
# task1 storage uses revenue/units_sold/avg_price/marketing_spend/inventory_level
METRIC_MAP = {
    'revenue':          'revenue',
    'units_sold':       'units_sold',
    'avg_order_value':  'avg_price',
    'traffic':          None,          # no direct Task1 equivalent, skip
}
df['metric_name'] = df['metric_name'].map(METRIC_MAP)
df = df[df['metric_name'].notna()].copy()

# Add product column (marketing_spend uses 'ALL', others use 'Product A')
df['product'] = df['metric_name'].apply(lambda m: 'ALL' if m == 'marketing_spend' else 'Product A')

# Keep only needed columns
insert_df = df[['date', 'region', 'product', 'metric_name', 'value']].copy()
insert_df['date'] = insert_df['date'].astype(str)
insert_df['value'] = insert_df['value'].round(2)

print(f"  Mapped to {len(insert_df)} insertable rows")
print(f"  Metrics: {insert_df['metric_name'].unique().tolist()}")
print(f"  Regions: {insert_df['region'].unique().tolist()}")

# Check existing data
conn = sqlite3.connect(str(DB_PATH))
existing = conn.execute("SELECT COUNT(*) FROM metrics_table").fetchone()[0]
print(f"  Existing rows in DB: {existing}")

if existing > 5000:
    print("  DB already has long history (>5000 rows), skipping seed.")
    conn.close()
else:
    insert_df.to_sql('metrics_table', conn, if_exists='append', index=False)
    conn.commit()
    new_count = conn.execute("SELECT COUNT(*) FROM metrics_table").fetchone()[0]
    print(f"  Done. DB now has {new_count} rows.")
    # Verify per-metric counts
    rows = conn.execute(
        "SELECT metric_name, COUNT(*) as n FROM metrics_table GROUP BY metric_name"
    ).fetchall()
    for metric, n in rows:
        print(f"    {metric}: {n} rows")

conn.close()
print("Seed complete. Prophet will now be active on /kpis (needs 60+ days per metric).")
