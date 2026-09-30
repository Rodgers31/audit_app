"""Exact three-row #379 reconciliation. No dotenv/default database, seed or gate bypass.

Prepare and default apply are READ ONLY. Commit requires a reviewed plan digest
and a durable recovery receipt written BEFORE any DML. Recovery uses that same
plan in reverse and refuses any intervening drift. Never invoke commit against
production without the owner's separate release authorization.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, select, text, update
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oag_prior_year_boundary_manifest as reviewed  # noqa: E402
from seeding.extractors.oag_blue_book import source_hash_of  # noqa: E402
from seeding.oag_discovery import fiscal_year_in_name  # noqa: E402
from services.audit_citations import audited_institution  # noqa: E402
from services.publication_gate import publishable_audit_criterion  # noqa: E402
from models import Audit, Country  # noqa: E402

MANIFEST_SHA256 = "8504dd3243d56a5de8b98eea717faf0c8de484be3e3b28a00b2c8342c0228961"
TABLES = ("source_documents", "entities", "fiscal_periods", "extractions", "audits")


def normalized(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def encoded(value):
    return (json.dumps(normalized(value), sort_keys=True, ensure_ascii=False,
                       indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def save_new(path, value):
    """Never overwrite a recovery receipt; failure occurs before DB mutation."""
    with Path(path).open("xb") as handle:
        handle.write(encoded(value))
        handle.flush()
        os.fsync(handle.fileno())
    directory = os.open(str(Path(path).resolve().parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


@lru_cache(maxsize=1)
def _source_payloads(pdf_path, pdf_sha):
    # The caller hashes bytes on EVERY invocation, including cache hits.
    pages = reviewed.current.read_pages(Path(pdf_path), ocr_enabled=False, visible_only=True)
    split = reviewed.county.split_volume(pages)
    old = reviewed.walk(pages, split, reviewed.legacy_parser())
    new = reviewed.walk(pages, split, reviewed.current)
    if len(split.chapters) != 47 or split.refused or len(old) != 582 or set(old) != set(new):
        raise ValueError("source finding coverage drift")
    changed = {k for k in old if old[k].finding_text != new[k].finding_text}
    if changed != set(reviewed.EXPECTED):
        raise ValueError("source text-change scope drift")
    for key in old:
        if {k: v for k, v in vars(old[key]).items() if k != "finding_text"} != {
            k: v for k, v in vars(new[key]).items() if k != "finding_text"
        }:
            raise ValueError("source metadata drift")
    return pages, split, old, new


def validate_source(pdf, manifest):
    raw_manifest = Path(manifest).read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != MANIFEST_SHA256:
        raise ValueError("manifest is not the exact reviewed manifest")
    raw_pdf = Path(pdf).read_bytes()
    pdf_sha = hashlib.sha256(raw_pdf).hexdigest()
    if pdf_sha != reviewed.SOURCE_SHA256:
        raise ValueError("PDF is not the exact reviewed source")
    # sha is rechecked before using the cache. Replays both parser versions and
    # verifies all 582 identities/metadata, not just three literal strings.
    source = _source_payloads(str(Path(pdf).resolve()), pdf_sha)
    return json.loads(raw_manifest), hashlib.md5(raw_pdf).hexdigest(), source


def tables_for(connection):
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=connection) for name in TABLES}


def snapshot(connection, tables, manifest, *, lock=False):
    a, x, s, e, p = (tables[n] for n in ("audits", "extractions", "source_documents", "entities", "fiscal_periods"))
    ids = [row["id"] for row in manifest["changed_rows"]]
    rows = connection.execute(select(a).where(a.c.id.in_(ids)).order_by(a.c.id)).mappings().all()
    if len(rows) != 3:
        raise ValueError("missing reviewed audit row")
    result = []
    for row in rows:
        item = {"audit": dict(row)}
        for name, table, key in (("extraction", x, row["extraction_id"]),
                                 ("source", s, row["source_document_id"]),
                                 ("entity", e, row["entity_id"]),
                                 ("period", p, row["period_id"])):
            query = select(table).where(table.c.id == key)
            if lock:
                query = query.with_for_update()
            item[name] = dict(connection.execute(query).mappings().one())
        # Bound identity/duplicate probes. The commit takes table locks before
        # these reads so an insert cannot evade the probe while we update.
        peers = connection.execute(select(a.c.id).where(
            (a.c.external_reference == row["external_reference"]) |
            (a.c.extraction_id == row["extraction_id"])
        ).limit(2)).scalars().all()
        payload = item["extraction"]["extracted_json"]
        if not isinstance(payload, dict):
            raise ValueError("malformed authoritative extraction")
        extractions = connection.execute(select(x.c.id).where(
            x.c.source_document_id == row["source_document_id"],
            x.c.extractor == reviewed.county.EXTRACTOR_ID,
            x.c.extracted_json["chapter_no"].astext == str(payload.get("chapter_no")),
            x.c.extracted_json["paragraph_no"].astext == str(payload.get("paragraph_no")),
        ).limit(2)).scalars().all()
        if peers != [row["id"]] or extractions != [row["extraction_id"]]:
            raise ValueError("duplicate reference/extraction identity")
        result.append(normalized(item))
    return result


def validate_rows(connection, manifest, md5, source, rows, *, after=False, lock=False):
    pages, split, old, new = source
    by_id = {r["audit"]["id"]: r for r in rows}
    for mr in manifest["changed_rows"]:
        item = by_id[mr["id"]]
        a, x, s, e, p = (item[k] for k in ("audit", "extraction", "source", "entity", "period"))
        payload = x["extracted_json"]
        key = next(k for k, v in reviewed.EXPECTED.items() if v[0] == mr["id"])
        ch = next(ch for ch in split.chapters if ch.no == key[0])
        stats = (s.get("metadata") or {}).get("extraction_stats") or {}
        discovery = (s.get("metadata") or {}).get("oag_discovery") or {}
        fy, fy_sources = reviewed.county.resolve_fiscal_year(
            in_text=split.fiscal_year_in_text, discovered=discovery.get("fiscal_year"),
            in_filename=fiscal_year_in_name((s["url"] or "").rsplit("/", 1)[-1]))
        expected = reviewed.county.finding_to_extracted_json(
            ch, (new if after else old)[key], fiscal_year=fy, fiscal_year_sources=fy_sources,
            kind="assemblies", county=re.sub(r"\s+County$", "", mr["preserved_fields"]["county_name"]),
            printed_page=mr["source_printed_page"])
        provenance = {"source": x["extractor"], "reference": mr["external_reference"],
                      "source_url": s["url"], "source_md5": s["md5"], "extraction_id": x["id"],
                      **{field: payload.get(field) for field in (
                          "pdf_page", "printed_page", "subreport", "opinion", "heading", "sub_section",
                          "title", "amounts", "extraction_method", "volume_kind", "chapter_no", "auditee", "fiscal_year_sources")}}
        side = mr["after" if after else "before"]
        if any((
            a["entity_id"] != mr["entity_id"], a["period_id"] != mr["period_id"],
            a["external_reference"] != mr["external_reference"], a["audit_year"] != mr["audit_year"],
            a["page_ref"] != mr["page_ref"], a["finding_text"] != side["text"],
            hashlib.sha256(a["finding_text"].encode()).hexdigest() != side["sha256"],
            a["source_hash"] != source_hash_of(payload),
            s["url"] != manifest["source_url"], s["md5"] != md5,
            s["publisher"] != "Office of the Auditor-General", s["doc_type"] != "AUDIT",
            s["status"] != "AVAILABLE", (s.get("metadata") or {}).get("extracted_md5") != md5,
            stats.get("findings") != 582, stats.get("volume_kind") != "assemblies",
            discovery.get("kind") != "assemblies", e["canonical_name"] != mr["preserved_fields"]["county_name"],
            e["type"] != "COUNTY", e["country_id"] != s["country_id"], p["country_id"] != s["country_id"],
            p["label"] != "FY2024/25", not p["start_date"].startswith("2024-07-01T00:00:00"),
            not p["end_date"].startswith("2025-06-30T"),
            x["source_document_id"] != s["id"], x["page_number"] != mr["source_pdf_page"],
            x["extractor"] != reviewed.county.EXTRACTOR_ID, encoded(payload) != encoded(expected),
            encoded(a["provenance"]) != encoded([provenance]),
            audited_institution(payload, county_name=e["canonical_name"], document_meta=s["metadata"]) != mr["audited_entity_name"],
            a["publishable"] is not True, a["quarantine_reason"] is not None,
        )):
            raise ValueError(f"source/identity/payload drift on audit {mr['id']}")
        for field in ("severity", "query_type", "amount", "status"):
            expected_value = mr["preserved_fields"][field]
            if field == "severity":
                expected_value = expected_value.upper()
            if field == "query_type":
                # Public snapshot uses a display label; storage retains the
                # exact source subreport. Validate against replayed evidence.
                expected_value = expected["subreport"]
            if a[field] != expected_value:
                raise ValueError(f"reviewed field drift: {field}")
        eligible = connection.execute(select(Audit.id).where(
            Audit.id == mr["id"], publishable_audit_criterion())).scalar_one_or_none()
        if eligible != mr["id"]:
            raise ValueError("shared publication gate refuses reviewed audit")
    # The manifest's institution IDs are Kenyan rows, not globally unique
    # county names. Keep the country declaration locked through a commit.
    countries = {item["source"]["country_id"] for item in rows}
    country_query = select(Country.iso_code).where(Country.id.in_(countries))
    if lock:
        country_query = country_query.with_for_update(read=True)
    if len(countries) != 1 or connection.execute(country_query).scalar_one() != "KEN":
        raise ValueError("Kenyan institutional scope drift")


def make_plan(connection, tables, manifest, md5, source):
    before = snapshot(connection, tables, manifest)
    validate_rows(connection, manifest, md5, source, before)
    after = copy.deepcopy(before)
    replacements = {r["id"]: r["after"]["text"] for r in manifest["changed_rows"]}
    for item in after:
        payload = item["extraction"]["extracted_json"]
        payload["finding_text"] = replacements[item["audit"]["id"]]
        item["audit"]["finding_text"] = payload["finding_text"]
        item["audit"]["source_hash"] = source_hash_of(payload)
    return {"schema": "oag_boundary_correction/v1", "manifest_sha256": MANIFEST_SHA256,
            "source_sha256": manifest["source_sha256"], "before": before, "after": after}


def run(engine, pdf, manifest_path, *, plan=None, expected_plan_sha256=None,
        commit=False, recover=False, receipt_path=None):
    """All guards live here too: direct Python callers cannot bypass the CLI."""
    if type(commit) is not bool or type(recover) is not bool:
        raise ValueError("commit/recover require booleans")
    if engine.dialect.name != "postgresql":
        raise ValueError("requires PostgreSQL")
    if (commit or recover) and plan is None:
        raise ValueError("commit/recovery requires an exact reviewed plan")
    if plan is not None and (not isinstance(plan, dict) or digest(plan) != expected_plan_sha256):
        raise ValueError("reviewed plan digest mismatch")
    if commit and receipt_path is None:
        raise ValueError("commit requires a durable recovery receipt")
    manifest, md5, source = validate_source(pdf, manifest_path)
    with engine.connect() as connection:
        connection.execute(text("BEGIN" if commit else "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        try:
            if not commit and connection.execute(text("SHOW transaction_read_only")).scalar_one() != "on":
                raise ValueError("read-only transaction not enforced")
            connection.execute(text("SET LOCAL statement_timeout = '8s'"))
            connection.execute(text("SET LOCAL lock_timeout = '2s'"))
            if commit:
                # Blocks concurrent inserts and writers during the bounded
                # three-row reconciliation; no broad data update or scan.
                connection.execute(text("LOCK TABLE audits, extractions IN SHARE ROW EXCLUSIVE MODE"))
            tables = tables_for(connection)
            if plan is None:
                return make_plan(connection, tables, manifest, md5, source)
            current = snapshot(connection, tables, manifest, lock=commit)
            validate_rows(connection, manifest, md5, source, current, after=recover, lock=commit)
            # Reconstruct the canonical forward plan from the guarded before
            # snapshot, never trust arbitrary replacement fields in a receipt.
            forward_before = copy.deepcopy(current)
            if recover:
                for item, mr in zip(forward_before, manifest["changed_rows"], strict=True):
                    item["audit"]["finding_text"] = mr["before"]["text"]
                    item["extraction"]["extracted_json"]["finding_text"] = mr["before"]["text"]
                    item["audit"]["source_hash"] = source_hash_of(item["extraction"]["extracted_json"])
            canonical = {"schema": "oag_boundary_correction/v1", "manifest_sha256": MANIFEST_SHA256,
                         "source_sha256": manifest["source_sha256"], "before": forward_before,
                         "after": copy.deepcopy(forward_before)}
            for item, mr in zip(canonical["after"], manifest["changed_rows"], strict=True):
                item["extraction"]["extracted_json"]["finding_text"] = mr["after"]["text"]
                item["audit"]["finding_text"] = mr["after"]["text"]
                item["audit"]["source_hash"] = source_hash_of(item["extraction"]["extracted_json"])
            if encoded(canonical) != encoded(plan):
                raise ValueError("stored row or recovery-plan drift")
            target = plan["before" if recover else "after"]
            if commit:
                save_new(receipt_path, {"schema": "oag_boundary_recovery/v1", "plan_sha256": digest(plan),
                                       "plan": plan, "direction": "recover" if recover else "correct",
                                       "commit_status": "intent_only_check_database_for_outcome"})
                for item in target:
                    a, x = item["audit"], item["extraction"]
                    connection.execute(update(tables["extractions"]).where(tables["extractions"].c.id == x["id"])
                                       .values(extracted_json=x["extracted_json"]))
                    connection.execute(update(tables["audits"]).where(tables["audits"].c.id == a["id"])
                                       .values(finding_text=a["finding_text"], source_hash=a["source_hash"]))
                actual = snapshot(connection, tables, manifest)
                if encoded(actual) != encoded(target):
                    raise ValueError("postwrite snapshot drift; rolled back")
                validate_rows(connection, manifest, md5, source, actual, after=not recover)
                connection.commit()
            return {"plan_sha256": digest(plan), "direction": "recover" if recover else "correct",
                    "outcome": "committed" if commit else "read_only_dry_run", "audit_ids": [r["id"] for r in manifest["changed_rows"]]}
        finally:
            if connection.in_transaction():
                connection.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Dedicated explicit variable; never load .env or fall back to DATABASE_URL.
    raw = os.environ["OAG_BOUNDARY_DATABASE_URL"]
    url = make_url(raw)
    if url.get_backend_name() != "postgresql" or url.query:
        raise ValueError("explicit PostgreSQL URL without query options required")
    engine = create_engine(url, connect_args={"connect_timeout": 8})
    try:
        plan = json.loads(args.plan.read_bytes()) if args.plan else None
        if plan and plan.get("schema") == "oag_boundary_recovery/v1":
            plan = plan["plan"]
        result = run(engine, args.pdf, args.manifest, plan=plan,
                     expected_plan_sha256=args.expected_plan_sha256, commit=args.commit,
                     recover=args.recover, receipt_path=args.output if args.commit else None)
        if not args.commit:
            save_new(args.output, result)
        print(json.dumps({"outcome": result.get("outcome", "prepared_read_only"),
                          "plan_sha256": result.get("plan_sha256", digest(result))}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
