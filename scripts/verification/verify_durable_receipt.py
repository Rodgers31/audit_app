#!/usr/bin/env python3
"""Guarded prospective Supabase acceptance; run put and read in separate processes.

Never provisions a bucket, changes access, deletes bytes or upgrades historical
evidence. No automatic dotenv loading. Secret resolution uses the backend's
configured server secret manager only after explicit target checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from seeding.config import SeedingSettings
from services.receipt_store import configured_receipt_store
from services.supabase_receipt_store import ReceiptStorageError, validate_destination


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--expected-project-ref", required=True)
    cli.add_argument("--expected-bucket", required=True)
    operations = cli.add_subparsers(dest="operation", required=True)
    put = operations.add_parser(
        "put", help="Insert one bounded file and verify authenticated readback"
    )
    put.add_argument("--file", type=Path, required=True)
    put.add_argument("--allow-supabase-write", action="store_true")
    read = operations.add_parser(
        "read", help="Verify a retained digest in this fresh process"
    )
    read.add_argument("--digest", required=True)
    read.add_argument("--expected-size", type=int, required=True)
    return cli


def verify(args, settings: SeedingSettings) -> dict:
    if settings.receipt_storage_backend != "supabase":
        raise ValueError("Acceptance requires the selected Supabase backend")
    destination = validate_destination(
        settings.receipt_supabase_url, settings.receipt_supabase_bucket
    )
    if (
        destination != f"https://{args.expected_project_ref}.supabase.co"
        or settings.receipt_supabase_bucket != args.expected_bucket
    ):
        raise ValueError(
            "Acceptance target does not match the explicit project and bucket"
        )
    limit = settings.receipt_max_bytes
    if type(limit) is not int or not 1 <= limit <= 64 * 1024 * 1024:
        raise ValueError("Acceptance requires an explicit bounded byte limit")
    if args.operation == "put":
        if not args.allow_supabase_write:
            raise ValueError("Acceptance put requires --allow-supabase-write")
        with args.file.open("rb") as source:
            body = source.read(limit + 1)
        if not body or len(body) > limit:
            raise ValueError("Acceptance file empty or exceeds byte limit")
        store = configured_receipt_store(settings)
        digest = store.put(body)
        size = len(body)
    elif args.operation == "read":
        if type(args.expected_size) is not int or not 1 <= args.expected_size <= limit:
            raise ValueError("Acceptance expected size invalid")
        store = configured_receipt_store(settings)
        body = store.read(args.digest)
        digest = args.digest
        size = len(body)
        if size != args.expected_size or hashlib.sha256(body).hexdigest() != digest:
            raise ReceiptStorageError("Acceptance digest or size mismatch")
    else:
        raise ValueError("Unknown acceptance operation")
    return {
        "status": "authenticated_readback_matched",
        "operation": args.operation,
        "project_ref": args.expected_project_ref,
        "bucket": args.expected_bucket,
        "digest": digest,
        "byte_size": size,
        "scope": "configured storage byte check; retention and disaster recovery require separate acceptance",
    }


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        result = verify(args, SeedingSettings())
    except (OSError, ValueError, ReceiptStorageError):
        # Config/IO exceptions can contain untrusted input; omit their contents.
        print(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "configuration, target, file or storage check failed",
                }
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
