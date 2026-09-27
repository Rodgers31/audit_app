import os
import random
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict

import psycopg2
import yaml

LOCK_KEY = 874321  # arbitrary advisory lock id


def pg_advisory_lock(conn):
    cur = conn.cursor()
    cur.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,))
    ok = cur.fetchone()[0]
    cur.close()
    return ok


def pg_advisory_unlock(conn):
    cur = conn.cursor()
    cur.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
    cur.close()


def load_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def run_once(env: Dict[str, str]):
    # Small wrapper to run incremental backfill with env filters.
    # NOTE: Parliament is NOT routed here — it is owned exclusively by
    # APScheduler in backend/main.py to avoid dual-scheduler execution.
    from subprocess import run

    args = ["python", "-m", "etl.backfill"]
    run(args, env={**os.environ, **env}, check=False)


def schedule_worker():
    cfg_path = os.getenv("ETL_SCHEDULE_CONFIG", "/app/config/etl_schedule.yaml")
    db_url = os.getenv("DATABASE_URL")
    run_on_start = os.getenv("ETL_RUN_ON_START", "true").lower() in ("1", "true", "yes")
    if not db_url:
        print("DATABASE_URL is required")
        time.sleep(10)
        return

    cfg = load_config(cfg_path)
    # Example cfg schema:
    # countries:
    #   KE:
    #     sources:
    #       cob: { interval_hours: 12, jitter_minutes: 20 }
    #       treasury: { interval_hours: 24 }
    #       oag: { interval_hours: 24 }

    schedule: Dict[str, Dict[str, Any]] = {}
    now = datetime.utcnow()
    for country, ccfg in (cfg.get("countries") or {}).items():
        scfg = ccfg.get("sources") or {}
        for source, sc in scfg.items():
            interval_h = int(sc.get("interval_hours", 24))
            schedule_key = f"{country}:{source}"
            # If run_on_start, set next=now so all sources fire immediately
            if run_on_start:
                next_run = now
            else:
                next_run = now + timedelta(
                    # nondeterminism-ok: scheduler jitter delays a source's first run; never published
                    minutes=random.randint(0, int(sc.get("jitter_minutes", 30)))
                )
            schedule[schedule_key] = {
                "interval": timedelta(hours=interval_h),
                "next": next_run,
                "env": {
                    "BACKFILL_SOURCES": source,
                    "COUNTRY_CODE": country,
                    # add per-source concurrency or year filters as needed
                },
            }

    if run_on_start:
        print("[worker] ETL_RUN_ON_START=true — all sources will scrape immediately")

    while True:
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            if not pg_advisory_lock(conn):
                # Another worker holds the lock
                time.sleep(15)
                conn.close()
                continue

            try:
                now = datetime.utcnow()
                for key, item in schedule.items():
                    if now >= item["next"]:
                        country, source = key.split(":", 1)
                        print(
                            f"[worker] running {country}/{source} at {now.isoformat()}Z"
                        )
                        # Run job in a short-lived thread to not block scheduling loop
                        t = threading.Thread(
                            target=run_once,
                            kwargs={"env": item["env"]},
                        )
                        t.start()
                        # schedule next
                        item["next"] = now + item["interval"]
                time.sleep(30)
            finally:
                pg_advisory_unlock(conn)
                conn.close()
        except Exception as e:
            print("[worker] error:", e)
            time.sleep(10)


if __name__ == "__main__":
    schedule_worker()
