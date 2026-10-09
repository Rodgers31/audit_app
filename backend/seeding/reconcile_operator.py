"""Explicit operator session. No runtime dispatch activation or quiescence flag.

Open this direct connection before an independently authorized maintenance fence.
Then submit distinct JSON requests: {action:plan,evidence:...} and
{action:apply,evidence:...,plan:...}. Policy is deployed separately at startup,
never supplied by a request. Loss of this process/backend requires a new plan.
"""
import json
import os
from pathlib import Path
import stat
import sys
from hashlib import sha256

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from seeding.reconciliation import (MAX_BYTES, ReconciliationRefused, apply_plan,
                                    canonical, inspect_context, make_plan, shape)


def load_policy():
    # This is deployment configuration, not an evidence/CLI argument. The hash
    # must be provisioned independently and reviewed with the writer inventory.
    path = Path(os.environ["AUDIT_RECONCILIATION_POLICY_PATH"])
    expected = os.environ["AUDIT_RECONCILIATION_POLICY_SHA256"]
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or info.st_size > MAX_BYTES:
        raise ReconciliationRefused("Trusted deployment policy file required")
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ReconciliationRefused("Deployment policy fingerprint mismatch")
    policy = json.loads(raw)
    canonical(policy)
    return policy


def request(connection, policy, value):
    if type(value) is not dict or value.get("action") not in ("inspect", "plan", "apply"):
        raise ReconciliationRefused("Explicit inspect, plan or apply action required")
    if value["action"] == "inspect":
        shape(value, ("action", "selector"))
        return {"status": "inspected", "inspection": inspect_context(connection, value["selector"])}
    if value["action"] == "plan":
        shape(value, ("action", "evidence"))
        return {"status": "planned", "plan": make_plan(connection, policy, value["evidence"])}
    shape(value, ("action", "evidence", "plan"))
    return apply_plan(connection, policy, value["evidence"], value["plan"])


def main():
    try:
        policy = load_policy()
        url = os.environ["AUDIT_RECONCILIATION_DIRECT_DATABASE_URL"]
        engine = create_engine(url, poolclass=NullPool)
        with engine.connect() as connection:
            connection.execute(text("SET search_path = public"))
            connection.execute(text("SET TimeZone = 'UTC'"))
            connection.commit()
            print(json.dumps({"status": "connected", "instruction": "Establish independently authorized database admission and host/scheduler fences before planning."}), flush=True)
            while True:
                line = sys.stdin.buffer.readline(MAX_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_BYTES:
                    raise ReconciliationRefused("Request exceeds bound")
                try:
                    result = request(connection, policy, json.loads(line))
                except (ReconciliationRefused, ValueError, TypeError, KeyError):
                    connection.rollback()
                    result = {"status": "refused", "message": "Request/evidence/plan unverified; no release committed."}
                print(json.dumps(result, sort_keys=True), flush=True)
        engine.dispose()
        return 0
    except SQLAlchemyError:
        # Includes ambiguous commit. Never promise retention, reconnect or retry.
        print(json.dumps({"status": "uncertain", "message": "Database transaction continuity lost. Inspect durable audit and ownership before a new session; do not retry apply."}), flush=True)
        return 2
    except (ReconciliationRefused, ValueError, TypeError, KeyError, OSError):
        print(json.dumps({"status": "refused", "message": "Operator deployment configuration unverified."}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
