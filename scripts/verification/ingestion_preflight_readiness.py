#!/usr/bin/env python3
"""Retained B65 planning facts and interface to the existing operating evaluator."""
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import sys

sys.dont_write_bytecode = True
if __package__:
    from . import evaluate_social_operating_budget as budget
else:
    import evaluate_social_operating_budget as budget

HOLDS = (
    "REPRESENTATIVE_ACTIVE_SOURCE_AND_BACKUP_TRAFFIC",
    "PROVIDER_METER_CUTOFF_CALLER_ATTRIBUTION",
    "FULL_CLIENT_PEAK_AND_OPERATOR_RESERVE",
    "MEMORY_WARNING_778_AND_SHARED_500MB_RAM",
    "RECURRING_OWNER_MANAGED_OFFSITE_BACKUP_POLICY",
    "STORAGE_RETENTION_RECOVERY_AND_INACTIVITY_POLICY",
    "OWNER_PLAN_DECISION_AND_FRESH_CUSTODY",
)


def readiness(packet=None, *, expected_identity=None, as_of=None):
    """No new acceptance verifier: delegate complete evidence to the existing one.

    B65 cycle bytes include older releases/diagnostics; never extrapolate them as
    an optimized daily rate. Imported artifacts remain operator assertions.
    """
    result = {
        "status": "BLOCKED",
        "free_ready": False,
        "production_authorized": False,
        "plan_change_authorized": False,
        "generator_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "generated_by": "scripts/verification/ingestion_preflight_readiness.py",
        "retained_evidence": "B65, 23 October 2026; not a fresh provider read",
        "retained": {
            "database_bytes": 90_100_000,
            "uncached_cycle_bytes": 43_126_000_000,
            "cached_cycle_bytes": 0,
            "mau": 1,
            "optimized_daily_rate_bytes": None,
        },
        "official_free_limits": {
            "database_bytes": 500_000_000,
            "uncached_bytes": 5_000_000_000,
            "cached_bytes_separate": 5_000_000_000,
            "storage_bytes": 1_000_000_000,
            "mau": 50_000,
            "shared_ram_mb": 500,
            "inactive_pause_days": 7,
        },
        "historical_uncached_allowance_multiple": "8.6252",
        "current_database_headroom_bytes_before_growth_and_reserve": 409_900_000,
        "forecast_interface": {
            "evaluator": "scripts/verification/evaluate_social_operating_budget.py",
            "required_inputs": ["packet", "expected_identity", "explicit_as_of"],
            "source_projection": "future_increments workload=nightly; measured bytes, units, overlap/inclusion and receipt required",
            "backup_projection": "separate owner-approved measured recurring backup traffic/storage/retention forecast; currently absent",
            "protocol_bytes": "proxy only; not provider-billed bytes",
            "selected_decoded_bytes": "cannot qualify billed transfer or Free readiness",
        },
        "existing_operating_evaluation": None,
        "unmet_gates": list(HOLDS),
        "errors": [],
        "preserve": [
            "current Supabase plan and spend cap",
            "Vercel $1 PauseOn",
            "publishing/uploads/native/supervision/Actions OFF",
            "owner export custody deadline 2026-10-28T21:45:54-05:00",
        ],
    }
    if packet is None and expected_identity is None and as_of is None:
        result["errors"] = ["REPRESENTATIVE_EVIDENCE_ABSENT"]
    elif packet is None or expected_identity is None or type(as_of) is not datetime:
        result["errors"] = ["OPERATING_INPUTS_INCOMPLETE"]
    else:
        result["existing_operating_evaluation"] = budget.evaluate(
            packet, expected_identity=expected_identity, as_of=as_of
        )
    return result


def main(argv=None):
    try:
        parser = budget.SafeParser(description=__doc__)
        parser.add_argument("--packet", type=Path)
        parser.add_argument("--expected-identity", type=Path)
        parser.add_argument("--as-of")
        args = parser.parse_args(argv)
        result = readiness(
            budget.load_json(args.packet) if args.packet else None,
            expected_identity=budget.load_json(args.expected_identity)
            if args.expected_identity
            else None,
            as_of=budget.instant(args.as_of) if args.as_of else None,
        )
        print(budget.canonical(result).decode())
        return 1  # This planning interface never makes an activation decision.
    except Exception:
        print('{"status":"BLOCKED","free_ready":false,"errors":["INPUT_REFUSED"]}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
