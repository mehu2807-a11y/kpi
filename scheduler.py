"""
scheduler.py — lightweight daily cron wrapper for the KPI pipeline.

Runs orchestrate.run_end_to_end() for each KPI × region combination
on a daily cadence (default: 06:00 local time). Appends confirmed
anomalies to historical_precedent_log.jsonl, closing the feedback
loop with Task 4's query_historical_precedent().

Usage:
  python scheduler.py           # runs on cron schedule indefinitely
  python scheduler.py --now     # runs once immediately and exits
  python scheduler.py --dry-run # prints what would run, does nothing

Requires: pip install schedule (already in requirements.txt or add it)
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / 'orchestrator'))
sys.path.insert(0, str(PROJECT_ROOT / 'task1'))
sys.path.insert(0, str(PROJECT_ROOT / 'task3'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [scheduler] %(levelname)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

PRECEDENT_LOG_PATH = str(PROJECT_ROOT / 'historical_precedent_log.jsonl')
KPIS_TO_WATCH = [
    {'kpi_id': 'revenue_total', 'metric': 'revenue', 'region': 'Region X', 'product': 'Product A'},
    {'kpi_id': 'units_sold',    'metric': 'units_sold', 'region': 'Region X', 'product': 'Product A'},
    {'kpi_id': 'avg_price',     'metric': 'avg_price',  'region': 'Region X', 'product': 'Product A'},
    {'kpi_id': 'marketing_spend', 'metric': 'marketing_spend', 'region': 'Region X', 'product': 'ALL'},
    {'kpi_id': 'inventory_level', 'metric': 'inventory_level', 'region': 'Region X', 'product': 'Product A'},
]

def run_pipeline_once(dry_run: bool = False) -> dict:
    """
    Runs the full pipeline for each KPI in KPIS_TO_WATCH.
    Returns a summary dict: {kpi_id: {verdict, event_id (if anomaly), error}}
    """
    logger.info('Starting pipeline run for %d KPIs', len(KPIS_TO_WATCH))
    summary = {}
    
    if dry_run:
        for kpi in KPIS_TO_WATCH:
            logger.info('[dry-run] Would check: kpi=%s region=%s', kpi['kpi_id'], kpi['region'])
            summary[kpi['kpi_id']] = {'verdict': 'dry_run'}
        return summary
    
    try:
        # Load metrics table from Task 1
        from scoped_import import scoped_task_dir
        with scoped_task_dir(str(PROJECT_ROOT / 'task1')):
            from ingest_pipeline import storage
        metrics_table = storage.query(str(PROJECT_ROOT / 'task1' / 'bi_pipeline.db'), 'SELECT * FROM metrics_table')
        metrics_table['date'] = metrics_table['date'].astype(str)
    except Exception as e:
        logger.error('Failed to load metrics table: %s', e)
        return {'error': str(e)}
    
    try:
        from scoped_import import scoped_task_dir
        with scoped_task_dir(str(PROJECT_ROOT / 'task1')):
            from ingest_pipeline import storage as _storage
        doc_rows = _storage.query(str(PROJECT_ROOT / 'task1' / 'bi_pipeline.db'), 'SELECT * FROM document_store').to_dict('records')
    except Exception as e:
        logger.warning('Failed to load document store (using empty): %s', e)
        doc_rows = []
    
    # Load historical precedent log from disk
    try:
        from task4.correlate_drivers import load_precedent_log
        historical_log = load_precedent_log(PRECEDENT_LOG_PATH)
    except Exception:
        historical_log = []
    
    from orchestrator.orchestrate import run_end_to_end
    import anomaly_gate as T3
    import numpy as np
    import pandas as pd
    
    for kpi_def in KPIS_TO_WATCH:
        kpi_id = kpi_def['kpi_id']
        metric = kpi_def['metric']
        region = kpi_def['region']
        product = kpi_def['product']
        
        try:
            series = metrics_table[
                (metrics_table['region'] == region) &
                (metrics_table['product'] == product) &
                (metrics_table['metric_name'] == metric)
            ].sort_values('date')
            
            if len(series) < 7:
                logger.info('KPI %s: insufficient data (%d rows)', kpi_id, len(series))
                summary[kpi_id] = {'verdict': 'insufficient_data', 'rows': len(series)}
                continue
            
            values = series['value'].to_numpy()
            pre = values[:-5] if len(values) > 5 else values
            window = pre[-30:]
            mu = window.mean()
            sigma = window.std() or (mu * 0.02)
            
            history = T3.RegionHistory()
            config = T3.GateConfig()
            event_counter = T3.EventCounter()
            record = None
            for date_str, val in zip(series['date'], values):
                check = T3.MetricCheck(
                    date=date_str, region=region, metric=kpi_id,
                    actual_value=float(val), expected_value=mu,
                    lower_bound=mu - 2.5 * sigma, upper_bound=mu + 2.5 * sigma,
                )
                record, internal = T3.run_gate(check, [], history, config, event_counter)
                history.push(internal)
            
            verdict = record['verdict'] if record else 'unknown'
            logger.info('KPI %s: verdict=%s', kpi_id, verdict)
            summary[kpi_id] = {'verdict': verdict}
            
            if verdict == 'anomaly':
                event_id = record.get('event_id', f'evt_{kpi_id}_{datetime.now().strftime("%Y%m%d%H%M")}')
                summary[kpi_id]['event_id'] = event_id
                # Write to precedent log for future reference
                _write_precedent_entry(event_id, record, kpi_id, PRECEDENT_LOG_PATH)
        
        except Exception as exc:
            logger.error('KPI %s failed: %s', kpi_id, exc)
            summary[kpi_id] = {'verdict': 'error', 'error': str(exc)}
    
    logger.info('Pipeline run complete: %s', json.dumps({k: v.get('verdict') for k, v in summary.items()}))
    return summary

def _write_precedent_entry(event_id: str, record: dict, kpi_id: str, path: str) -> None:
    """
    Writes a minimal precedent entry to the JSONL log when an anomaly is confirmed.
    The signature is a placeholder (flat equal weights) until an analyst confirms the cause;
    feedback_manager updates this later.
    """
    try:
        from task4.correlate_drivers import append_incident_to_log, CANDIDATE_FEATURES
        signature = {f: round(1.0 / len(CANDIDATE_FEATURES), 3) for f in CANDIDATE_FEATURES}
        incident = {
            'event_id': event_id,
            'date': record.get('date', datetime.now().date().isoformat()),
            'kpi_id': kpi_id,
            'confirmed_cause': 'pending_analyst_review',
            'signature': signature,
            'auto_logged': True,
            'logged_at': datetime.now().isoformat(),
        }
        append_incident_to_log(incident, path)
        logger.info('Wrote precedent entry for %s to %s', event_id, path)
    except Exception as exc:
        logger.warning('Failed to write precedent entry: %s', exc)

def schedule_daily(run_time: str = '06:00') -> None:
    """Schedule the pipeline to run daily at run_time."""
    try:
        import schedule
    except ImportError:
        logger.error('schedule package not installed. Run: pip install schedule')
        sys.exit(1)
    
    schedule.every().day.at(run_time).do(run_pipeline_once)
    logger.info('Scheduled daily pipeline run at %s', run_time)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def main():
    parser = argparse.ArgumentParser(description='KPI Pipeline Scheduler')
    parser.add_argument('--now', action='store_true', help='Run once immediately and exit')
    parser.add_argument('--dry-run', action='store_true', help='Print what would run, do nothing')
    parser.add_argument('--time', type=str, default='06:00', help='Daily run time (HH:MM, default 06:00)')
    args = parser.parse_args()
    
    if args.dry_run:
        result = run_pipeline_once(dry_run=True)
        print(json.dumps(result, indent=2))
        return
    
    if args.now:
        result = run_pipeline_once(dry_run=False)
        print(json.dumps(result, indent=2, default=str))
        return
    
    schedule_daily(run_time=args.time)

if __name__ == '__main__':
    main()
