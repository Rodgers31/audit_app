"""Bounded replay of discovered OAG volumes on an existing disposable clone.

Requires a loopback database named codex_oag_*. Never creates, restores or drops
one. Each volume runs in a subprocess (900s wall / 6 GiB RSS); the existing
PDF downloader banks bytes and the existing extraction/load transaction owns
all evidence writes. A completed receipt means local rehearsal, not production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def local_engine():
    raw = os.environ["OAG_REHEARSAL_DATABASE_URL"]
    url = make_url(raw)
    if (url.drivername not in {"postgresql", "postgresql+psycopg2"} or url.query
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or not (url.database or "").startswith("codex_oag_")):
        raise ValueError("Rehearsal requires a loopback codex_oag_* database")
    return create_engine(raw)


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n")


def worker(args, volume):
    from models import Country, DocumentType
    from seeding.config import SeedingSettings
    from seeding.domains.audits.loader import load_blue_book_extractions
    from seeding.extractors.oag_county_audit import extract_county_audit
    from seeding.extractors.reconciliation import extract_and_load, record_failed_attempt
    from seeding.fetch_documents import fetch_document
    from seeding.http_client import create_http_client
    from seeding.types import DomainRunContext

    settings = SeedingSettings(cache_path=args.artifacts / "cache", storage_path=args.artifacts / "data",
        http_cache_enabled=False, timeout_seconds=20, pdf_download_max_bytes=40 * 1024 * 1024,
        audits_ocr_enabled=False)
    started = time.monotonic()
    receipt = {"scope": "disposable_local_clone", "volume": volume}
    with Session(local_engine()) as session, create_http_client(settings) as client:
        country = session.query(Country).filter_by(iso_code="KEN").one()
        doc = fetch_document(session, client, settings, url=volume["url"], country_id=country.id,
            publisher="Office of the Auditor-General", title=volume["url"].rsplit("/", 1)[-1],
            doc_type=DocumentType.AUDIT, dataset_id="oag_county_audits", max_seconds=120)
        doc.meta = {**(doc.meta or {}), "oag_discovery": {k: v for k, v in volume.items() if k != "url"}}
        session.commit()
        receipt.update(document_id=doc.id, sha256=hashlib.sha256(Path(doc.file_path).read_bytes()).hexdigest(), md5=doc.md5)
        try:
            extracted, loaded = extract_and_load(session, doc, settings,
                DomainRunContext(since=None, dry_run=False), extract_county_audit, load_blue_book_extractions)
            session.commit()
            receipt.update(extracted=extracted, loaded=vars(loaded), document_metadata=doc.meta,
                           outcome="partial" if extracted.get("partial") or loaded.errors or loaded.skipped else "completed")
        except Exception as exc:
            receipt.update(outcome="refused", attempt=record_failed_attempt(doc, exc))
            session.commit()
        receipt["wall_seconds"] = round(time.monotonic() - started, 3)
        save(args.artifacts / f"volume-{args.worker}.json", receipt)


def run(args, volumes, discovery):
    from models import Audit, IngestionJob, IngestionStatus
    from seeding.county_audit_coverage import county_audit_coverage_receipt, coverage_verdict

    # The row hashes detect any change to pre-existing evidence, including rows
    # outside the selected volumes. This rehearsal grants no retirement review.
    def fingerprints(session):
        return {a.id: hashlib.sha256(json.dumps({c.name: getattr(a, c.key) for c in Audit.__table__.columns},
                sort_keys=True, default=str).encode()).hexdigest() for a in session.query(Audit)}

    started = datetime.now(timezone.utc)
    with Session(local_engine()) as session:
        before = fingerprints(session)
        save(args.artifacts / "coverage-before.json", county_audit_coverage_receipt(session))
    report = dict(discovered=len(volumes), processed=[], already_current=[], deferred=[], failed=[], partial=[])
    docs = []
    for index, volume in enumerate(volumes):
        label = f"{volume['fiscal_year']} {volume['kind']}"
        if not args.all_listed and volume["fiscal_year"] != volumes[0]["fiscal_year"]:
            report["deferred"].append(label)
            continue
        receipt_file = args.artifacts / f"volume-{index}.json"
        receipt_file.unlink(missing_ok=True)
        with (args.artifacts / f"volume-{index}.log").open("w") as log:
            process = subprocess.Popen([sys.executable, __file__, "--manifest", str(args.manifest),
                "--artifacts", str(args.artifacts), "--worker", str(index)], stdout=log, stderr=subprocess.STDOUT)
            began = time.monotonic()
            max_rss = 0
            while process.poll() is None:
                raw = subprocess.run(["ps", "-o", "rss=", "-p", str(process.pid)], capture_output=True, text=True).stdout.strip()
                rss = int(raw or 0) * 1024
                max_rss = max(max_rss, rss)
                if time.monotonic() - began > 900 or rss > 6 * 1024**3:
                    process.kill()
                    process.wait()
                    break
                time.sleep(1)
        if process.returncode or not receipt_file.exists():
            report["failed"].append(f"{label}: worker failed/resource limit; see volume-{index}.log")
            continue
        receipt = json.loads(receipt_file.read_text())
        receipt["max_rss_bytes"] = max_rss
        save(receipt_file, receipt)
        extracted = receipt.get("extracted", {})
        docs.append({"doc_id": receipt.get("document_id"), "extractions": extracted})
        if receipt["outcome"] != "completed":
            report["partial" if receipt["outcome"] == "partial" else "failed"].append(label)
        elif extracted.get("reason") in ("already_extracted", "already_extracted_by_delegate"):
            report["already_current"].append(label)
        else:
            report["processed"].append(f"{label}: {extracted.get('created')} finding(s)")
        print(label, receipt["outcome"], flush=True)
    with Session(local_engine()) as session:
        after = fingerprints(session)
        preserved = all(after.get(key) == value for key, value in before.items())
        session.add(IngestionJob(domain="audits", dry_run=False, started_at=started,
            status=IngestionStatus.COMPLETED if not (report["failed"] or report["partial"]) else IngestionStatus.FAILED,
            meta={"execution_scope": "disposable_local_clone", "oag_county_discovery": discovery["metadata"],
                  "county_volumes": report, "documents": docs}))
        session.commit()
        coverage = county_audit_coverage_receipt(session)
        save(args.artifacts / "coverage-after.json", coverage)
        save(args.artifacts / "run-receipt.json", {"scope": "disposable_local_clone", "started_at": started,
            "county_volumes": report, "coverage_verdict": coverage_verdict(coverage),
            "prior_audit_rows": len(before), "after_audit_rows": len(after), "prior_audits_unchanged": preserved})
        if not preserved:
            raise RuntimeError("Pre-existing audit evidence changed; inspect local clone")
        if report["failed"] or report["partial"]:
            raise SystemExit(1)
        if coverage_verdict(coverage)[0] != "OK":
            # A successful bounded subset is not national coverage.
            raise SystemExit(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--all-listed", action="store_true")
    parser.add_argument("--worker", type=int)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    discovery = json.loads(args.manifest.read_text())
    volumes = sorted((d for d in discovery["documents"] if d["kind"] in ("executives", "assemblies")),
                     key=lambda d: (-int(d["fiscal_year"][:4]), d["kind"] == "assemblies", d["url"]))
    local_engine()  # refuse a nonlocal destination before launching anything
    if args.worker is not None:
        worker(args, volumes[args.worker])
    else:
        run(args, volumes, discovery)
