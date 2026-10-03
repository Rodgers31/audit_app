"""Source-bound FY2020/21 OAG completion; every invocation defaults to ROLLBACK.

Only Source2395/2396 metadata may change. No ingestion, row replacement, new
source/entity, job, listing refresh or publication is performed. Commit requires
the coordinator's reviewed plan digest and a durable exclusive recovery receipt.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import bindparam, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts/verification"))
from oag_boundary_correction import cli_engine, encoded, normalized, save_new
from seeding.extractors import oag_blue_book as bb

MANIFEST = ROOT / "docs/operations/2026-10-03-round21-older-oag/completion-plan.json"
MANIFEST_SHA256 = "25c967eda9143bb8be38f82a1f01754ee9962654ca249142f722eb1a5d0f26e0"
TABLES = ("audits", "budget_lines", "debt_instruments", "debt_timeline",
          "economic_indicators", "entities", "extractions", "fiscal_summaries",
          "gdp_data", "loans", "parliament_source_documents", "population_data",
          "poverty_indices", "revenue_by_source", "source_documents")
IDS = (2395, 2396)
SCHEMA = "oag_older_completion_execution/v1"


def sha(value):
    # Same canonical hash used by the fresh root capture's scoped cohort plan.
    return hashlib.sha256(json.dumps(normalized(value), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def same(a, b):
    return encoded(a) == encoded(b)


def manifest():
    raw = MANIFEST.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError("unreviewed older-source authority")
    value = json.loads(raw)
    if ([s.get("source_id") for s in value["sources"]] != list(IDS)
            or set(value["protected"]) != set(TABLES)):
        raise ValueError("older-source authority scope changed")
    return value


def source_proof(authority, pdfs):
    """Run the actual complete reader; cached caller-supplied verdicts are unused."""
    if not same(authority, manifest()):
        raise ValueError("source proof requires the exact reviewed authority")
    if not isinstance(pdfs, dict) or set(pdfs) != set(IDS):
        raise ValueError("both exact older PDFs required")
    reader_hash = hashlib.sha256(Path(bb.__file__).read_bytes()).hexdigest()
    if reader_hash != authority["reader_sha256"]:
        raise ValueError("reviewed reader bytes changed")
    proofs = []
    for entry in authority["sources"]:
        sid = entry["source_id"]
        path = Path(pdfs[sid])
        raw = path.read_bytes()
        if (hashlib.sha256(raw).hexdigest() != entry["pdf_sha256"]
                or hashlib.md5(raw).hexdigest() != entry["pdf_md5"]):
            raise ValueError("older source PDF identity changed")
        pages = bb.read_pages(path, ocr_enabled=True, ocr_max_pages=30)
        result = bb.parse_blue_book(pages, entry["source_before"]["url"])
        payloads = [bb.finding_to_extracted_json(f, result.fiscal_year_label)
                    for f in result.findings]
        counts = Counter(p["vote"] for p in payloads)
        if (len(pages) != entry["page_count"] or result.votes_seen != 47
                or len(bb.parse_toc(pages)) != 47 or result.skipped_votes
                or result.rejected_cid or any(p.method == "rejected" for p in pages)
                or result.fiscal_year_label != "2020/2021"
                or set(counts) != set(range(1, 48))
                or len(payloads) != entry["findings"]
                or len({bb.blue_book_row_key(p) for p in payloads}) != len(payloads)
                or sha(payloads) != entry["candidate_payloads_sha256"]):
            raise ValueError("older-source extraction incomplete or changed")
        if path.read_bytes() != raw:
            raise ValueError("PDF changed during extraction")
        proofs.append({"source_id": sid, "payloads": payloads,
                       "pdf_sha256": entry["pdf_sha256"], "pages": len(pages)})
    return {"schema": "oag_older_complete_source_proof/v1",
            "reader_sha256": reader_hash, "sources": proofs}


def rows(connection, table, *, source=False):
    field = "source_document_id" if source else "id"
    query = text(f"SELECT to_jsonb(t) AS row FROM public.{table} t "
                 f"WHERE {field} IN :ids ORDER BY id FOR UPDATE").bindparams(
                     bindparam("ids", expanding=True))
    return [r[0] for r in connection.execute(query, {"ids": list(IDS)})]


def protection(connection, after_sources=None, before=None):
    result = {}
    for table in TABLES:
        if after_sources is not None and table != "source_documents":
            result[table] = before[table]
            continue
        expression = "to_jsonb(t)"
        params = {}
        if table == "source_documents" and after_sources is not None:
            expression += " || CASE id "
            for i, row in enumerate(after_sources):
                expression += f"WHEN :id{i} THEN jsonb_build_object('metadata',CAST(:meta{i} AS jsonb)) "
                params[f"id{i}"] = row["id"]
                params[f"meta{i}"] = json.dumps(row["metadata"], allow_nan=False)
            expression += "ELSE '{}'::jsonb END"
        count, value = connection.execute(text(
            "SELECT count(*),encode(sha256(convert_to(coalesce("
            "string_agg(length(row_text)::text || ':' || row_text,'' ORDER BY id),''),"
            f"'UTF8')),'hex') FROM (SELECT id,({expression})::text AS row_text "
            f"FROM public.{table} t) image"), params).one()
        result[table] = {"count": count, "sha256": value}
    return result


def sequences(connection):
    return [dict(r) for r in connection.execute(text(
        "SELECT schemaname,sequencename,last_value FROM pg_sequences "
        "WHERE schemaname='public' ORDER BY sequencename")).mappings()]


def validate_current(connection, authority, proof, inverse=False):
    if not same(authority, manifest()):
        raise ValueError("cohort validation requires the exact reviewed authority")
    if (not isinstance(proof, dict) or proof.get("schema") != "oag_older_complete_source_proof/v1"
            or proof.get("reader_sha256") != authority["reader_sha256"]
            or [s.get("source_id") for s in proof.get("sources", [])] != list(IDS)):
        raise ValueError("malformed source completion proof")
    source_rows = rows(connection, "source_documents")
    expected = []
    for entry in authority["sources"]:
        row = copy.deepcopy(entry["source_before"])
        if inverse:
            row["metadata"] = entry["metadata_after_existing_writer"]
        expected.append(row)
    if not same(source_rows, expected):
        raise ValueError("whole source image drift")
    extractions = rows(connection, "extractions", source=True)
    audits = rows(connection, "audits", source=True)
    for entry, real in zip(authority["sources"], proof["sources"], strict=True):
        sid = entry["source_id"]
        exts = [r for r in extractions if r["source_document_id"] == sid]
        ars = [r for r in audits if r["source_document_id"] == sid]
        if (sha(exts) != entry["extraction_rows_before_sha256"]
                or sha(ars) != entry["audit_rows_before_sha256"]
                or [r["id"] for r in exts] != entry["extraction_ids"]
                or [r["id"] for r in ars] != entry["audit_ids"]):
            raise ValueError("whole audit/extraction cohort drift")
        payloads = real.get("payloads")
        if (not isinstance(payloads, list) or sha(payloads) != entry["candidate_payloads_sha256"]
                or len(payloads) != len(exts)
                or real.get("pdf_sha256") != entry["pdf_sha256"]
                or type(real.get("pages")) is not int or real["pages"] != entry["page_count"]):
            raise ValueError("candidate proof mismatch")
        candidates = {bb.blue_book_row_key(p): p for p in payloads}
        if len(candidates) != len(payloads):
            raise ValueError("duplicate candidate key")
        for ext in exts:
            p = candidates.get(bb.blue_book_row_key(ext["extracted_json"]))
            if (not same(ext["extracted_json"], p) or ext["page_number"] != p["pdf_page"]
                    or not same(ext["confidence"], 0.6 if p["extraction_method"] == "ocr" else 0.9)
                    or ext["extractor"] != bb.EXTRACTOR_ID):
                raise ValueError("candidate would change stored finding")
    return source_rows


def run(engine, pdfs, *, commit=False, inverse=False, recovery=None,
        expected_recovery_sha256=None, expected_manifest_sha256=None, receipt_path=None):
    if type(commit) is not bool or type(inverse) is not bool or engine.dialect.name != "postgresql":
        raise ValueError("PostgreSQL and typed boolean modes required")
    authority = manifest()
    if inverse:
        if (not isinstance(recovery, dict) or sha(recovery) != expected_recovery_sha256
                or recovery.get("schema") != SCHEMA
                or recovery.get("direction") != "forward"
                or recovery.get("manifest_sha256") != MANIFEST_SHA256):
            raise ValueError("reviewed recovery receipt required")
    elif recovery is not None:
        raise ValueError("unexpected forward recovery input")
    if commit and (receipt_path is None or expected_manifest_sha256 != MANIFEST_SHA256):
        raise ValueError("reviewed manifest digest and durable exclusive receipt required for commit")
    proof = source_proof(authority, pdfs)
    with engine.connect() as connection:
        connection.execute(text("BEGIN ISOLATION LEVEL REPEATABLE READ"))
        try:
            connection.execute(text("SET LOCAL statement_timeout='8s'"))
            connection.execute(text("SET LOCAL lock_timeout='2s'"))
            connection.execute(text("LOCK TABLE " + ",".join("public." + t for t in TABLES)
                                    + " IN SHARE ROW EXCLUSIVE MODE"))
            before = validate_current(connection, authority, proof, inverse)
            protected = protection(connection)
            seq = sequences(connection)
            if not same(seq, authority["sequences"]):
                raise ValueError("sequence drift")
            expected_before = recovery["protected_after"] if inverse else authority["protected"]
            if not same(protected, expected_before):
                raise ValueError("protected before-image drift")
            original_projection = None
            if inverse:
                original_projection = protection(connection, [s["source_before"]
                    for s in authority["sources"]], protected)
                if not same(original_projection, authority["protected"]):
                    raise ValueError("inverse unrelated protection drift")
            after = []
            for entry in authority["sources"]:
                row = copy.deepcopy(entry["source_before"])
                if not inverse:
                    row["metadata"] = entry["metadata_after_existing_writer"]
                after.append(row)
            predicted = original_projection if inverse else protection(connection, after, protected)
            if inverse and not same(predicted, authority["protected"]):
                raise ValueError("recovery predicted image differs from authority")
            result = {"schema": SCHEMA, "manifest_sha256": MANIFEST_SHA256,
                      "direction": "inverse" if inverse else "forward",
                      "source_proof_sha256": sha(proof), "before": before, "after": after,
                      "protected_before": protected, "protected_after": predicted,
                      "sequences": seq, "outcome": "intent_check_database"}
            if inverse and (not same(recovery.get("after"), before)
                    or not same(recovery.get("before"), after)
                    or not same(recovery.get("protected_before"), authority["protected"])
                    or not same(recovery.get("sequences"), seq)):
                raise ValueError("recovery images differ from canonical authority")
            if commit:
                save_new(receipt_path, result)
            for row in after:
                changed = connection.execute(text(
                    "UPDATE public.source_documents SET metadata=CAST(:metadata AS jsonb) "
                    "WHERE id=:id"), {"metadata": json.dumps(row["metadata"], allow_nan=False),
                                       "id": row["id"]})
                if changed.rowcount != 1:
                    raise ValueError("source update count mismatch")
            if (not same(rows(connection, "source_documents"), after)
                    or not same(protection(connection), predicted)
                    or not same(sequences(connection), seq)):
                raise ValueError("postwrite full-image/protection drift")
            validate_current(connection, authority, proof, not inverse)
            if commit:
                connection.commit()
            result["outcome"] = "committed" if commit else "rolled_back"
            return result
        finally:
            if connection.in_transaction():
                connection.rollback()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executives-pdf", type=Path, required=True)
    parser.add_argument("--assemblies-pdf", type=Path, required=True)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--inverse", action="store_true")
    parser.add_argument("--recovery", type=Path)
    parser.add_argument("--expected-recovery-sha256")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = cli_engine(os.environ["OAG_OLDER_COMPLETION_DATABASE_URL"])
    try:
        result = run(engine, {2395: args.executives_pdf, 2396: args.assemblies_pdf},
                     commit=args.commit, inverse=args.inverse,
                     recovery=json.loads(args.recovery.read_bytes()) if args.recovery else None,
                     expected_recovery_sha256=args.expected_recovery_sha256,
                     expected_manifest_sha256=args.expected_manifest_sha256,
                     receipt_path=str(args.output) + ".intent.json" if args.commit else None)
        save_new(args.output, result)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
