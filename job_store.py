import sqlite3
import json
import time
import uuid
import os
import threading

# Use SQLite to share state across multiple Gunicorn workers.
# In-memory dicts fail if Render routes polling requests to a different worker.
DB_PATH = 'jobs.db'

# Ensure the DB schema exists
_init_lock = threading.Lock()
with _init_lock:
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT,
                created_at REAL,
                result TEXT,
                error TEXT
            )
        ''')

def create_job():
    job_id = str(uuid.uuid4())
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.execute(
            'INSERT INTO jobs (job_id, status, created_at) VALUES (?, ?, ?)',
            (job_id, 'pending', time.time())
        )
    return job_id

def update_job(job_id, status, result=None, error=None):
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        result_json = json.dumps(result) if result is not None else None
        conn.execute(
            'UPDATE jobs SET status = ?, result = ?, error = ? WHERE job_id = ?',
            (status, result_json, error, job_id)
        )

def get_job(job_id):
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,))
        row = cur.fetchone()
        if row:
            return {
                'status': row['status'],
                'created_at': row['created_at'],
                'result': json.loads(row['result']) if row['result'] else None,
                'error': row['error']
            }
        return None

def cleanup_old_jobs(max_age_seconds=1800): # 30 minutes default
    cutoff = time.time() - max_age_seconds
    with sqlite3.connect(DB_PATH, timeout=10.0) as conn:
        conn.execute('DELETE FROM jobs WHERE created_at < ?', (cutoff,))
