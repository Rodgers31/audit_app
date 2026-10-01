"""#380 exact CPI correction/recovery; default mode is enforced READ ONLY.

Use CPI_CORRECTION_DATABASE_URL explicitly. Live commit requires separate
release-owner approval. No default DATABASE_URL or dotenv is read. Reuses the
existing guarded correction receipt/hash/TLS infrastructure; no seed job runs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
from sqlalchemy import MetaData, Table, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
# Existing #379 executor owns these durable, URL-safe primitives. It is not
# invoked here and its OAG tables/parser/source validation remain untouched.
from oag_boundary_correction import cli_engine, digest, encoded, normalized, save_new
from models import EconomicIndicator
from services.publication_gate import (
    economic_publication_failure,
    cpi_extraction_digest,
)

MANIFEST_SHA256 = "543e1ad07a7c30081c93b51b74450c22883611656ec03ff2b6c5dd62dfa50722"
TABLES = ("economic_indicators", "source_documents", "extractions", "countries")
SCHEMA = "cpi_source_correction/v1"


def validate_source(manifest_path, pdfs):
    raw = Path(manifest_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("manifest is not the exact reviewed manifest")
    manifest = json.loads(raw)
    refs = manifest["source_documents_to_allocate_or_reuse"]
    if not isinstance(pdfs, dict) or set(pdfs) != set(refs):
        raise ValueError("both exact reviewed PDFs required")
    for ref, source in refs.items():
        raw_pdf = Path(pdfs[ref]).read_bytes()
        if (
            hashlib.sha256(raw_pdf).hexdigest() != source["sha256"]
            or hashlib.md5(raw_pdf).hexdigest() != source["md5"]
        ):
            raise ValueError("reviewed PDF hash mismatch")
        with pdfplumber.open(pdfs[ref]) as pdf:
            page = pdf.pages[source["page_number"] - 1].extract_text()
        if (
            not page
            or "Table 1: Overall CPI and Rates of Inflation" not in page
            or "Base Feb 2019=100" not in page
        ):
            raise ValueError("reviewed table/base unavailable")
        payload = manifest["extractions_to_allocate"][ref + "_table1"]["extracted_json"]
        if cpi_extraction_digest(payload) != source["reviewed_table1_sha256"]:
            raise ValueError("reviewed extraction digest conflict")
        observations = payload["observations"]
        for day, value in observations.items():
            month = datetime.fromisoformat(day).strftime("%B %Y")
            matches = re.findall(
                r"^" + re.escape(month) + r"\s+([0-9]+\.[0-9]+)\s+([0-9]+\.[0-9]+)\s*$",
                page,
                re.M,
            )
            if len(matches) != 1 or matches[0][0] != value:
                raise ValueError("reviewed Overall CPI column conflict")
    fixture = ROOT / manifest["fixture_prerequisite"]["file"]
    if (
        hashlib.sha256(fixture.read_bytes()).hexdigest()
        != manifest["fixture_prerequisite"]["deployed_file_sha256"]
    ):
        raise ValueError("retired CPI fixture prerequisite drift")
    return manifest


def tables_for(connection):
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=connection) for name in TABLES}


def snapshot(connection, tables, ids):
    table = tables["economic_indicators"]
    rows = (
        connection.execute(
            select(table).where(table.c.id.in_(ids)).order_by(table.c.id)
        )
        .mappings()
        .all()
    )
    if len(rows) != len(ids):
        raise ValueError("missing exact CPI identity")
    return normalized([dict(row) for row in rows])


def subset_matches(actual, expected):
    # Captured timestamp strings use spaces; reflected datetimes use ISO T.
    expected = copy.deepcopy(expected)
    for field in (
        "indicator_date",
        "created_at",
        "fetch_date",
        "last_seen_at",
        "last_verified_at",
    ):
        if expected.get(field):
            expected[field] = datetime.fromisoformat(expected[field]).isoformat()
    if any(actual.get(k) != v for k, v in expected.items()):
        raise ValueError("captured row/source preimage drift")


def source_values(source):
    stamp = datetime(2026, 9, 30)
    return dict(
        country_id=source["country_id"],
        publisher=source["publisher"],
        title=source["title"],
        url=source["url"],
        file_path=None,
        fetch_date=stamp,
        md5=source["md5"],
        doc_type="REPORT",
        status="AVAILABLE",
        content_type="application/pdf",
        http_status=200,
        last_verified_at=stamp,
        last_seen_at=stamp,
        created_at=stamp,
        metadata={
            "sha256": source["sha256"],
            "reviewed_table1_sha256": source["reviewed_table1_sha256"],
            "review_date": "2026-09-30",
        },
    )


def extraction_values(payload, source_id):
    return dict(
        source_document_id=source_id,
        page_number=payload["page_number"],
        extractor=payload["extractor"],
        confidence=None,
        extracted_json=payload["extracted_json"],
        created_at=datetime(2026, 9, 30),
    )


def candidates(connection, tables, manifest):
    """URL and page identities refuse duplicates/conflicts, never relabel them."""
    s, x = tables["source_documents"], tables["extractions"]
    documents, extractions = {}, {}
    for ref, source in manifest["source_documents_to_allocate_or_reuse"].items():
        matches = (
            connection.execute(select(s).where(s.c.url == source["url"]).limit(2))
            .mappings()
            .all()
        )
        if len(matches) > 1:
            raise ValueError("duplicate reviewed PDF URL")
        if matches:
            doc = normalized(dict(matches[0]))
            for key in (
                "country_id",
                "publisher",
                "title",
                "url",
                "md5",
                "doc_type",
                "content_type",
                "http_status",
            ):
                if doc[key] != source[key]:
                    raise ValueError("existing reviewed source conflict")
            if (
                doc["status"] != "AVAILABLE"
                or (doc.get("metadata") or {}).get("sha256") != source["sha256"]
                or (doc.get("metadata") or {}).get("reviewed_table1_sha256")
                != source["reviewed_table1_sha256"]
            ):
                raise ValueError("existing reviewed source hash/status conflict")
            documents[ref] = doc
        else:
            documents[ref] = None
        er = ref + "_table1"
        payload = manifest["extractions_to_allocate"][er]
        if not matches:
            extractions[er] = None
            continue
        matches_x = (
            connection.execute(
                select(x)
                .where(
                    x.c.source_document_id == doc["id"],
                    x.c.page_number == payload["page_number"],
                )
                .limit(2)
            )
            .mappings()
            .all()
        )
        if len(matches_x) > 1:
            raise ValueError("duplicate reviewed table extraction")
        if matches_x:
            ext = normalized(dict(matches_x[0]))
            if (
                ext["extractor"] != payload["extractor"]
                or ext["extracted_json"] != payload["extracted_json"]
                or ext["confidence"] is not None
            ):
                raise ValueError("existing reviewed extraction conflict")
            extractions[er] = ext
        else:
            extractions[er] = None
    return documents, extractions


def assert_exact_identity(connection, table, row):
    # PostgreSQL's NULL entity uniqueness does not prevent national duplicates.
    peers = (
        connection.execute(
            select(table.c.id)
            .where(
                table.c.indicator_type == row["indicator_type"],
                table.c.indicator_date == datetime.fromisoformat(row["indicator_date"]),
                table.c.entity_id.is_(None),
            )
            .limit(2)
        )
        .scalars()
        .all()
    )
    if peers != [row["id"]]:
        raise ValueError("duplicate exact CPI type/date/scope")


def assert_original_context(connection, tables, plan):
    source = tables["source_documents"]
    for row in plan["original_sources"]:
        actual = normalized(
            dict(
                connection.execute(select(source).where(source.c.id == row["id"]))
                .mappings()
                .one()
            )
        )
        if actual != row:
            raise ValueError("original shared source drift")
    country = tables["countries"]
    actual = normalized(
        dict(
            connection.execute(select(country).where(country.c.id == 1))
            .mappings()
            .one()
        )
    )
    if actual != plan["country"]:
        raise ValueError("original country context drift")


def make_plan(connection, tables, manifest):
    ids = [u["row_id"] for u in manifest["updates"]]
    before = snapshot(connection, tables, ids)
    by_id = {row["id"]: row for row in before}
    after = []
    for u in manifest["updates"]:
        subset_matches(by_id[u["row_id"]], u["before"])
        row = copy.deepcopy(by_id[u["row_id"]])
        row.update(normalized(u["after"]))
        for field in ("indicator_date", "created_at"):
            row[field] = datetime.fromisoformat(row[field]).isoformat()
        after.append(row)
        assert_exact_identity(
            connection, tables["economic_indicators"], by_id[u["row_id"]]
        )
    s = tables["source_documents"]
    originals = normalized(
        [
            dict(r)
            for r in connection.execute(
                select(s)
                .where(s.c.id.in_(manifest["unchanged_sources"]))
                .order_by(s.c.id)
            ).mappings()
        ]
    )
    if len(originals) != 2:
        raise ValueError("missing original shared source")
    for actual, expected in zip(
        originals, manifest["before_evidence"]["sources"], strict=True
    ):
        subset_matches(actual, expected)
    country = (
        connection.execute(
            select(tables["countries"]).where(tables["countries"].c.id == 1)
        )
        .mappings()
        .one()
    )
    if country["iso_code"] != "KEN":
        raise ValueError("Kenyan source scope drift")
    docs, exts = candidates(connection, tables, manifest)
    return dict(
        schema=SCHEMA,
        manifest_sha256=MANIFEST_SHA256,
        before=before,
        after=after,
        original_sources=originals,
        country=normalized(dict(country)),
        documents=docs,
        extractions=exts,
    )


def db_values(table, row):
    result = copy.deepcopy(row)
    for column in table.columns:
        if column.type.python_type is datetime and result.get(column.name):
            result[column.name] = datetime.fromisoformat(result[column.name])
    return result


def refuse_insert_proof(connection):
    connection.execute(text("SAVEPOINT cpi_readonly_proof"))
    try:
        connection.execute(text("INSERT INTO economic_indicators DEFAULT VALUES"))
    except DBAPIError as exc:
        if getattr(exc.orig, "pgcode", None) != "25006":
            raise ValueError(
                "read-only INSERT not refused by transaction policy"
            ) from None
    else:
        raise ValueError("read-only INSERT unexpectedly allowed")
    finally:
        connection.execute(text("ROLLBACK TO SAVEPOINT cpi_readonly_proof"))
        connection.execute(text("RELEASE SAVEPOINT cpi_readonly_proof"))


def assert_publication(connection, ids):
    # Execute the same reader gate before certifying an approved correction.
    if ids != [67, 86, 87]:
        raise ValueError("exact nonempty reviewed publication identities required")
    with Session(bind=connection) as db:
        rows = db.query(EconomicIndicator).filter(EconomicIndicator.id.in_(ids)).all()
        if len(rows) != len(ids) or {r.id for r in rows} != set(ids):
            raise ValueError("missing publication identity")
        for row in rows:
            if economic_publication_failure(row, db):
                raise ValueError("public CPI source chain refuses correction")


def apply(connection, tables, manifest, plan, receipt_path):
    # Intent survives any crash before resolution. Fully resolved receipt is
    # fsynced BEFORE COMMIT, so a lost commit acknowledgement is recoverable.
    save_new(
        receipt_path,
        dict(
            schema="cpi_correction_intent/v1",
            plan=plan,
            plan_sha256=digest(plan),
            commit_status="intent_only_check_database_for_outcome",
        ),
    )
    docs, exts = {}, {}
    allocated = {"source_documents": [], "extractions": []}
    for ref, source in manifest["source_documents_to_allocate_or_reuse"].items():
        doc = plan["documents"][ref]
        if doc is None:
            doc = normalized(
                dict(
                    connection.execute(
                        tables["source_documents"]
                        .insert()
                        .values(**source_values(source))
                        .returning(tables["source_documents"])
                    )
                    .mappings()
                    .one()
                )
            )
        docs[ref] = doc["id"]
        allocated["source_documents"].append(doc)
        er = ref + "_table1"
        ext = plan["extractions"][er]
        if ext is None:
            ext = normalized(
                dict(
                    connection.execute(
                        tables["extractions"]
                        .insert()
                        .values(
                            **extraction_values(
                                manifest["extractions_to_allocate"][er], doc["id"]
                            )
                        )
                        .returning(tables["extractions"])
                    )
                    .mappings()
                    .one()
                )
            )
        exts[er] = ext["id"]
        allocated["extractions"].append(ext)
    target = copy.deepcopy(plan["after"])
    for row in target:
        row["source_document_id"] = docs[
            row["source_document_id"]["allocated_document_ref"]
        ]
        row["extraction_id"] = exts[row["extraction_id"]["allocated_extraction_ref"]]
        values = db_values(tables["economic_indicators"], row)
        values.pop("id")
        connection.execute(
            update(tables["economic_indicators"])
            .where(tables["economic_indicators"].c.id == row["id"])
            .values(**values)
        )
    actual = snapshot(connection, tables, [r["id"] for r in target])
    if encoded(actual) != encoded(target):
        raise ValueError("postwrite snapshot drift; rolled back")
    assert_original_context(connection, tables, plan)
    assert_publication(connection, [r["id"] for r in target])
    resolved = dict(
        schema="cpi_correction_recovery/v1",
        plan=plan,
        plan_sha256=digest(plan),
        after=actual,
        allocations=allocated,
        commit_status="prepared_before_commit_check_database_for_outcome",
    )
    save_new(str(receipt_path) + ".resolved.json", resolved)
    return resolved


def recover(connection, tables, manifest, receipt, *, commit, receipt_path):
    if receipt.get("schema") != "cpi_correction_recovery/v1":
        raise ValueError("recovery receipt schema mismatch")
    plan = receipt["plan"]
    if (
        plan.get("schema") != SCHEMA
        or plan.get("manifest_sha256") != MANIFEST_SHA256
        or digest(plan) != receipt["plan_sha256"]
    ):
        raise ValueError("recovery plan identity mismatch")
    ids = [u["row_id"] for u in manifest["updates"]]
    if [r["id"] for r in receipt["after"]] != ids or snapshot(
        connection, tables, ids
    ) != receipt["after"]:
        raise ValueError("recovery full after-image drift")
    for row in receipt["after"]:
        assert_exact_identity(connection, tables["economic_indicators"], row)
    candidates(connection, tables, manifest)
    assert_original_context(connection, tables, plan)
    # Do not trust a caller-supplied before-image, even with a caller-supplied digest.
    for actual, u in zip(plan["before"], manifest["updates"], strict=True):
        subset_matches(actual, u["before"])
    restored = []
    for before, u in zip(plan["before"], manifest["updates"], strict=True):
        symbolic = copy.deepcopy(before)
        symbolic.update(normalized(u["after"]))
        for field in ("indicator_date", "created_at"):
            symbolic[field] = datetime.fromisoformat(symbolic[field]).isoformat()
        restored.append(symbolic)
    if restored != plan["after"]:
        raise ValueError("recovery canonical plan mismatch")
    # Validate the resolved IDs against the canonical source/extraction references.
    docs = {r["url"]: r for r in receipt["allocations"]["source_documents"]}
    ext_by_id = {r["id"]: r for r in receipt["allocations"]["extractions"]}
    if len(docs) != 2 or len(ext_by_id) != 2:
        raise ValueError("recovery allocation scope mismatch")
    for after, symbolic in zip(receipt["after"], plan["after"], strict=True):
        source = manifest["source_documents_to_allocate_or_reuse"][
            symbolic["source_document_id"]["allocated_document_ref"]
        ]
        doc = docs[source["url"]]
        ext = ext_by_id[after["extraction_id"]]
        payload = manifest["extractions_to_allocate"][
            symbolic["extraction_id"]["allocated_extraction_ref"]
        ]
        if (
            doc["md5"] != source["md5"]
            or doc["metadata"].get("sha256") != source["sha256"]
            or doc["publisher"] != source["publisher"]
            or doc["country_id"] != 1
            or ext["source_document_id"] != doc["id"]
            or ext["page_number"] != 2
            or ext["extracted_json"] != payload["extracted_json"]
        ):
            raise ValueError("recovery source/extraction allocation conflict")
        symbolic = copy.deepcopy(symbolic)
        symbolic["source_document_id"] = doc["id"]
        symbolic["extraction_id"] = ext["id"]
        if symbolic != after:
            raise ValueError("recovery resolved canonical after mismatch")
    for name in ("source_documents", "extractions"):
        t = tables[name]
        for row in receipt["allocations"][name]:
            current = normalized(
                dict(
                    connection.execute(select(t).where(t.c.id == row["id"]))
                    .mappings()
                    .one()
                )
            )
            if current != row:
                raise ValueError("recovery allocated evidence drift")
    s = tables["source_documents"]
    for row in plan["original_sources"]:
        if (
            normalized(
                dict(
                    connection.execute(select(s).where(s.c.id == row["id"]))
                    .mappings()
                    .one()
                )
            )
            != row
        ):
            raise ValueError("recovery shared source drift")
    assert_publication(connection, ids)
    if commit:
        save_new(
            receipt_path,
            dict(
                schema="cpi_recovery_intent/v1",
                recovery_sha256=digest(receipt),
                before=receipt["after"],
                after=plan["before"],
                commit_status="intent_only_check_database_for_outcome",
            ),
        )
        for row in plan["before"]:
            values = db_values(tables["economic_indicators"], row)
            values.pop("id")
            connection.execute(
                update(tables["economic_indicators"])
                .where(tables["economic_indicators"].c.id == row["id"])
                .values(**values)
            )
        if snapshot(connection, tables, ids) != plan["before"]:
            raise ValueError("recovery postwrite drift; rolled back")
    return dict(
        direction="recover",
        outcome="committed" if commit else "read_only_dry_run",
        row_ids=ids,
    )


def run(
    engine,
    manifest_path,
    pdfs,
    *,
    plan=None,
    expected_sha256=None,
    commit=False,
    recover_receipt=None,
    receipt_path=None,
):
    if type(commit) is not bool or engine.dialect.name != "postgresql":
        raise ValueError("requires boolean commit and PostgreSQL")
    reviewed = recover_receipt if recover_receipt is not None else plan
    if reviewed is not None and (
        not isinstance(reviewed, dict) or digest(reviewed) != expected_sha256
    ):
        raise ValueError("reviewed plan/receipt digest mismatch")
    if commit and (reviewed is None or receipt_path is None):
        raise ValueError("commit requires exact reviewed plan and durable receipt")
    if recover_receipt is not None and plan is not None:
        raise ValueError("ambiguous forward/recovery inputs")
    manifest = validate_source(manifest_path, pdfs)
    with engine.connect() as connection:
        connection.execute(
            text(
                "BEGIN" if commit else "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
        )
        try:
            connection.execute(text("SET LOCAL statement_timeout='8s'"))
            connection.execute(text("SET LOCAL lock_timeout='2s'"))
            if commit:
                connection.execute(
                    text(
                        "LOCK TABLE economic_indicators,source_documents,extractions,countries IN SHARE ROW EXCLUSIVE MODE"
                    )
                )
            else:
                if (
                    connection.execute(text("SHOW transaction_read_only")).scalar_one()
                    != "on"
                ):
                    raise ValueError("read-only transaction not enforced")
                refuse_insert_proof(connection)
            tables = tables_for(connection)
            if recover_receipt is not None:
                result = recover(
                    connection,
                    tables,
                    manifest,
                    recover_receipt,
                    commit=commit,
                    receipt_path=receipt_path,
                )
            else:
                canonical = make_plan(connection, tables, manifest)
                if plan is None:
                    return canonical
                if encoded(canonical) != encoded(plan):
                    raise ValueError("stored full preimage/plan drift")
                if commit:
                    resolved = apply(connection, tables, manifest, plan, receipt_path)
                    result = dict(
                        outcome="committed",
                        plan_sha256=digest(plan),
                        recovery_sha256=digest(resolved),
                        row_ids=[r["id"] for r in plan["before"]],
                    )
                else:
                    result = dict(outcome="read_only_dry_run", plan_sha256=digest(plan))
            if commit:
                connection.commit()
            return result
        finally:
            if connection.in_transaction():
                connection.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--january-pdf", type=Path, required=True)
    parser.add_argument("--december-pdf", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--recovery", type=Path)
    parser.add_argument("--expected-sha256")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = cli_engine(os.environ["CPI_CORRECTION_DATABASE_URL"])
    try:
        result = run(
            engine,
            args.manifest,
            dict(knbs_jan2025=args.january_pdf, knbs_dec2024=args.december_pdf),
            plan=json.loads(args.plan.read_bytes()) if args.plan else None,
            recover_receipt=json.loads(args.recovery.read_bytes())
            if args.recovery
            else None,
            expected_sha256=args.expected_sha256,
            commit=args.commit,
            receipt_path=args.output,
        )
        if not args.commit:
            save_new(args.output, result)
        print(
            json.dumps(
                {
                    "outcome": result.get(
                        "outcome", "prepared_check_database_for_outcome"
                    ),
                    "sha256": digest(result),
                }
            )
        )
    finally:
        engine.dispose()


def cli():
    try:
        main()
    except Exception as exc:
        print(f"CPI source correction failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    cli()
