"""Root-operated read-only images around #379 and the pinned OAG catch-up.

Protected rows remain on the server: count/schema/full-row SHA256 aggregates
are transferred. This is operation preservation, not a backup or public proof.
No publisher requests, job writes, extraction or publication occur here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oag_boundary_correction as boundary
from seeding.domains.audits.observation import accepted_editions, verify_adopted_volume
from seeding.domains.audits.scope import parse_manifest, read_manifest
from seeding import oag_discovery as od

TABLES = ("source_documents", "extractions", "audits", "entities", "countries", "fiscal_periods")
AUDITS = (5545, 5679, 5716)
EXTRACTIONS = (6023, 6158, 6196)
PINS = ("backend/tests/fixtures/oag_boundary_reviewed_manifest.json",
        "docs/operations/2026-10-01-round11-oag-catchup/manifest.json",
        "backend/seeding/domains/audits/accepted-source-manifest.json",
        "backend/seeding/domains/audits/observation.py",
        "backend/seeding/county_audit_coverage.py",
        "scripts/verification/oag_boundary_correction.py")


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_columns():
    from models import SourceDocument, Extraction, Audit, Entity, Country, FiscalPeriod
    return {m.__tablename__: {c.name for c in m.__table__.columns} for m in (SourceDocument, Extraction, Audit, Entity, Country, FiscalPeriod)}


def _rows(connection, table, ids):
    query = text(f"SELECT * FROM public.{table} WHERE id IN :ids ORDER BY id").bindparams(bindparam("ids", expanding=True))
    return [boundary.normalized(dict(r)) for r in connection.execute(query, {"ids": ids}).mappings()]


def capture(connection, stage, operation, *, coverage=False):
    if stage not in ("trim", "catchup") or not isinstance(operation, str) or not operation.strip():
        raise ValueError("explicit stage and operation identity required")
    if type(coverage) is not bool or coverage and stage != "catchup":
        raise ValueError("coverage is a catch-up after-state check")
    proof = connection.execute(text("SELECT current_setting('transaction_read_only'), current_setting('transaction_isolation')")).one()
    if tuple(proof) != ("on", "repeatable read"):
        raise ValueError("verified read-only repeatable-read required")
    selected = parse_manifest(read_manifest(ROOT / PINS[1]))
    selected_urls = {r["source_url"] for r in selected}
    editions = accepted_editions()
    sources = connection.execute(text("SELECT * FROM public.source_documents WHERE url IN :urls ORDER BY id").bindparams(bindparam("urls", expanding=True)), {"urls": list(editions)}).mappings().all()
    by_url = {r["url"]: boundary.normalized(dict(r)) for r in sources}
    if len(sources) != 8 or set(by_url) != set(editions):
        raise ValueError("actual eight source identities missing or duplicated")
    countries = dict(connection.execute(text("SELECT id, iso_code FROM public.countries")).all())
    if any(countries.get(s["country_id"]) != "KEN" for s in sources):
        raise ValueError("source country differs from Kenya")
    country_id = sources[0]["country_id"]
    counties = dict(connection.execute(text("SELECT id,canonical_name FROM public.entities WHERE type='COUNTY' AND country_id=:country"), {"country": country_id}).all())
    if len(counties) != 47:
        raise ValueError("actual Kenya county identities incomplete")
    selected_ids = sorted(by_url[url]["id"] for url in selected_urls)
    exclusions = {"audits": ("id", AUDITS), "extractions": ("id", EXTRACTIONS)} if stage == "trim" else {
        "source_documents": ("id", selected_ids), "audits": ("source_document_id", selected_ids),
        "extractions": ("source_document_id", selected_ids)}
    protected = {}
    for table in TABLES:
        schema = [list(r) for r in connection.execute(text("SELECT column_name,data_type,udt_schema,udt_name,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name=:table ORDER BY ordinal_position"), {"table": table})]
        if not schema or "id" not in {r[0] for r in schema}:
            raise ValueError("missing protected table/identity")
        field, excluded = exclusions.get(table, ("id", []))
        where = f"WHERE {field} NOT IN :excluded OR {field} IS NULL" if excluded else ""
        # Same PostgreSQL full-row encoding as the accepted recovery inventory.
        query = text(f"SELECT count(*), encode(sha256(convert_to(coalesce(string_agg(length(row_text)::text || ':' || row_text,'' ORDER BY id),''),'UTF8')),'hex') FROM (SELECT id,to_jsonb(t)::text AS row_text FROM public.{table} t {where}) rows")
        if excluded:
            query = query.bindparams(bindparam("excluded", expanding=True))
        count, sha = connection.execute(query, {"excluded": list(excluded)} if excluded else {}).one()
        if count <= 0:
            raise ValueError("empty protected cohort cannot certify preservation")
        protected[table] = {"columns": schema, "count": count, "sha256": sha}
    identity = connection.execute(text("SELECT current_database(),inet_server_addr()::text,inet_server_port(),current_setting('server_version_num')")).one()
    image = {"schema": "oag_acceptance_image/v1", "stage": stage, "operation": operation,
             "captured_at": datetime.now(timezone.utc).isoformat(),
             "generator_sha256": file_sha(__file__), "pins": {p: file_sha(ROOT / p) for p in PINS},
             "database_identity_sha256": boundary.digest(list(identity)),
             "transaction": {"read_only": "on", "isolation": "repeatable read"},
             "source_country": {"id": country_id, "iso_code": "KEN"},
             "county_identities": {str(k): v for k, v in counties.items()},
             "sources": by_url, "selected_ids": selected_ids, "protected": protected,
             "trim_rows": {"audits": _rows(connection, "audits", AUDITS), "extractions": _rows(connection, "extractions", EXTRACTIONS)}}
    if len(image["trim_rows"]["audits"]) != 3 or len(image["trim_rows"]["extractions"]) != 3:
        raise ValueError("missing three reviewed trim identities")
    if coverage:
        from seeding.county_audit_coverage import county_audit_coverage_receipt, coverage_verdict
        with Session(bind=connection) as session:
            image["edition_proofs"] = [verify_adopted_volume(session, od.OagDocument(url, e["fiscal_year"], e["institution"], "year_page", f"{od.OAG_ORIGIN}/{e['fiscal_year'].replace('/', '-')}-county-government-audit-reports/")) for url, e in editions.items()]
            receipt = county_audit_coverage_receipt(session)
            level, message = coverage_verdict(receipt)
            image["coverage"] = {"receipt": receipt, "level": level, "message": message}
    validate_image(image)
    return image


def validate_image(image):
    if not isinstance(image, dict) or image.get("schema") != "oag_acceptance_image/v1":
        raise ValueError("invalid image schema")
    if image.get("stage") not in ("trim", "catchup") or image.get("transaction") != {"read_only": "on", "isolation": "repeatable read"}:
        raise ValueError("image stage/transaction invalid")
    if image.get("generator_sha256") != file_sha(__file__) or image.get("pins") != {p: file_sha(ROOT / p) for p in PINS}:
        raise ValueError("image producer or executed authority changed")
    for key in ("operation", "database_identity_sha256", "captured_at"):
        if not isinstance(image.get(key), str) or not image[key].strip():
            raise ValueError("missing image identity")
    if not re.fullmatch(r"[0-9a-f]{64}", image["database_identity_sha256"]):
        raise ValueError("invalid database identity hash")
    captured = datetime.fromisoformat(image["captured_at"])
    if captured.tzinfo is None or captured > datetime.now(timezone.utc):
        raise ValueError("invalid capture time")
    if set(image.get("protected", {})) != set(TABLES):
        raise ValueError("missing protected table")
    required_columns = model_columns()
    for table, value in image["protected"].items():
        if (not isinstance(value, dict) or type(value.get("count")) is not int or value["count"] <= 0
                or not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
                or not isinstance(value.get("columns"), list) or not value["columns"]):
            raise ValueError("invalid protected image")
        columns = value["columns"]
        if (any(not isinstance(c, list) or len(c) != 5 or any(not isinstance(v, str) or not v for v in c)
                or c[4] not in ("YES", "NO") for c in columns)
                or len({c[0] for c in columns}) != len(columns) or not required_columns[table].issubset({c[0] for c in columns})):
            raise ValueError("invalid full-column schema image")
    editions = accepted_editions()
    sources = image.get("sources")
    if not isinstance(sources, dict) or set(sources) != set(editions):
        raise ValueError("missing reviewed edition source")
    if any(not isinstance(v, dict) or type(v.get("id")) is not int or v["id"] <= 0 or v.get("url") != k for k, v in sources.items()):
        raise ValueError("invalid edition source identity")
    if (any(type(s.get("country_id")) is not int or s["country_id"] <= 0
            or s.get("publisher") != "Office of the Auditor-General" or s.get("doc_type") != "AUDIT" for s in sources.values())
            or len({s["country_id"] for s in sources.values()}) != 1):
        raise ValueError("invalid Kenya OAG source declaration")
    if len({s["id"] for s in sources.values()}) != 8:
        raise ValueError("duplicate edition source identity")
    country = image.get("source_country")
    counties = image.get("county_identities")
    if (not isinstance(country, dict) or type(country.get("id")) is not int or country.get("iso_code") != "KEN"
            or any(s["country_id"] != country["id"] for s in sources.values())
            or not isinstance(counties, dict) or len(counties) != 47
            or any(not isinstance(k, str) or not re.fullmatch(r"[1-9][0-9]*", k)
                   or not isinstance(v, str) or not v.strip() for k, v in counties.items())
            or len(set(counties.values())) != 47):
        raise ValueError("actual Kenya/county identity image incomplete")
    selected_urls = {e["source_url"] for e in parse_manifest(read_manifest(ROOT / PINS[1]))}
    ids = image.get("selected_ids")
    if not isinstance(ids, list) or any(type(i) is not int for i in ids) or ids != sorted(sources[u]["id"] for u in selected_urls):
        raise ValueError("selected image scope differs from reviewed manifest")
    rows = image.get("trim_rows")
    if not isinstance(rows, dict) or set(rows) != {"audits", "extractions"}:
        raise ValueError("missing trim images")
    for table, expected in (("audits", AUDITS), ("extractions", EXTRACTIONS)):
        values = rows[table]
        if not isinstance(values, list) or any(not isinstance(v, dict) or type(v.get("id")) is not int for v in values) or sorted(v["id"] for v in values) != sorted(expected):
            raise ValueError("wrong trim identities")


def compare(before, after, *, plan=None, expected_plan_sha256=None, require_coverage=False):
    validate_image(before); validate_image(after)
    if type(require_coverage) is not bool:
        raise ValueError("require_coverage must be boolean")
    if require_coverage and before["stage"] != "catchup":
        raise ValueError("coverage requires catch-up images")
    for key in ("operation", "stage", "database_identity_sha256", "selected_ids", "source_country", "county_identities"):
        if before[key] != after[key]:
            raise ValueError("capture target/scope changed")
    if datetime.fromisoformat(after["captured_at"]) < datetime.fromisoformat(before["captured_at"]):
        raise ValueError("after-image predates before-image")
    gaps = [f"protected {t} changed" for t in TABLES if before["protected"][t] != after["protected"][t]]
    for url, old in before["sources"].items():
        new = after["sources"][url]
        if any(old.get(k) != new.get(k) for k in ("id", "url", "country_id", "publisher", "doc_type")):
            gaps.append("reviewed source identity changed")
    if before["stage"] == "trim":
        if not isinstance(plan, dict) or boundary.digest(plan) != expected_plan_sha256 or plan.get("schema") != "oag_boundary_correction/v1":
            raise ValueError("exact reviewed trim plan required")
        manifest = json.loads((ROOT / PINS[0]).read_bytes())
        if (plan.get("manifest_sha256") != file_sha(ROOT / PINS[0])
                or plan.get("source_sha256") != manifest["source_sha256"]):
            raise ValueError("trim plan source authority differs")
        # A rehashed arbitrary plan cannot authorize changes to other columns.
        target = copy.deepcopy(before["trim_rows"])
        from seeding.extractors.oag_blue_book import source_hash_of
        for mr, audit, extraction in zip(manifest["changed_rows"], target["audits"], target["extractions"], strict=True):
            if (audit["id"] != mr["id"] or audit.get("source_document_id") != 2541
                    or audit.get("extraction_id") != extraction["id"]
                    or audit.get("finding_text") != mr["before"]["text"]
                    or extraction.get("source_document_id") != 2541
                    or not isinstance(extraction.get("extracted_json"), dict)
                    or extraction["extracted_json"].get("finding_text") != mr["before"]["text"]
                    or audit.get("source_hash") != source_hash_of(extraction["extracted_json"])):
                raise ValueError("actual trim before-image differs from reviewed text/identity")
            audit["finding_text"] = mr["after"]["text"]
            extraction["extracted_json"]["finding_text"] = mr["after"]["text"]
            audit["source_hash"] = source_hash_of(extraction["extracted_json"])
        if after["trim_rows"] != target:
            gaps.append("trim changed fields outside the exact three reviewed text/hash replacements")
        for side, image in (("before", before), ("after", after)):
            expected = plan[side]
            for table, key in (("audits", "audit"), ("extractions", "extraction")):
                rows = sorted([v[key] for v in expected], key=lambda v: v["id"])
                if image["trim_rows"][table] != rows:
                    gaps.append(f"trim {side} {table} differs from actual reviewed plan")
    else:
        if before["trim_rows"] != after["trim_rows"]:
            gaps.append("catch-up changed protected corrected text rows")
    if require_coverage:
        coverage = after.get("coverage")
        proofs = after.get("edition_proofs")
        if not isinstance(coverage, dict) or coverage.get("level") != "OK":
            gaps.append("qualified coverage not OK")
        else:
            receipt = coverage.get("receipt")
            cells = receipt.get("cells") if isinstance(receipt, dict) else None
            if (not isinstance(cells, list) or len(cells) != 376 or receipt.get("run_gaps") != []
                    or any(not isinstance(c, dict) or type(c.get("county_id")) is not int or c["county_id"] <= 0
                           or not isinstance(c.get("county"), str) or not c["county"].strip()
                           or type(c.get("findings")) is not int or c["findings"] <= 0 for c in cells)):
                gaps.append("376 complete qualified cells absent")
            else:
                years = {e["fiscal_year"] for e in accepted_editions().values()}
                counties = {c["county_id"] for c in cells}
                keys = {(c["county_id"], c.get("fiscal_year"), c.get("institution")) for c in cells}
                expected = {(c, fy, role) for c in counties for fy in years for role in ("executives", "assemblies")}
                from seeding.county_audit_coverage import coverage_verdict
                if (not isinstance(receipt.get("required_years"), list) or len(receipt["required_years"]) != len(years)
                        or set(receipt["required_years"]) != years or receipt.get("county_count") != 47
                        or receipt.get("expected_county_count") != 47
                        or counties != {int(i) for i in after["county_identities"]}
                        or any(c["county"] != after["county_identities"][str(c["county_id"])] for c in cells)
                        or keys != expected or len(keys) != 376 or coverage_verdict(receipt)[0] != "OK"):
                    gaps.append("qualified cells do not form 47 distinct counties x4 years x2 institutions")
        editions = accepted_editions()
        if (not isinstance(proofs, list) or len(proofs) != 8
                or any(not isinstance(p, dict) for p in proofs)
                or {p.get("url") for p in proofs} != set(editions)):
            gaps.append("all eight actual edition proofs absent")
        else:
            for proof in proofs:
                e = editions[proof["url"]]
                if (type(proof.get("source_document_id")) is not int
                        or proof["source_document_id"] != after["sources"][proof["url"]]["id"]
                        or any(proof.get(k) != e[k] for k in ("md5", "sha256", "fiscal_year"))
                        or proof.get("institution") != e["institution"]
                        or type(proof.get("chapters")) is not int or proof["chapters"] != 47
                        or type(proof.get("findings")) is not int or proof["findings"] <= 0
                        or type(proof.get("size_bytes")) is not int or proof["size_bytes"] <= 0
                        or not isinstance(proof.get("state_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", proof["state_sha256"])
                        or proof.get("binding") not in ("individual_pdf_artifacts", "legacy_extracted_md5_complete_parser")):
                    gaps.append("actual edition proof identity/completeness differs")
                    break
    return {"schema": "oag_acceptance_comparison/v1", "generator_sha256": file_sha(__file__),
            "before_sha256": boundary.digest(before), "after_sha256": boundary.digest(after),
            "stage": before["stage"], "gaps": gaps, "preservation_passed": not gaps,
            "full_validation_and_public_acceptance": "separate root results required"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--stage", choices=("trim", "catchup"), required=True)
    c.add_argument("--operation", required=True)
    c.add_argument("--coverage", action="store_true")
    p = sub.add_parser("compare")
    p.add_argument("--before", type=Path, required=True); p.add_argument("--after", type=Path, required=True)
    p.add_argument("--plan", type=Path); p.add_argument("--expected-plan-sha256")
    p.add_argument("--require-coverage", action="store_true")
    args = parser.parse_args()
    if args.output.exists() or args.output.parent.stat().st_mode & 0o077:
        raise ValueError("new receipt in private0700 directory required")
    if args.command == "capture":
        engine = boundary.cli_engine(os.environ["OAG_ACCEPTANCE_DATABASE_URL"])
        try:
            with engine.connect() as connection:
                connection.execute(text("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY"))
                try:
                    connection.execute(text("SET LOCAL statement_timeout='15s'"))
                    connection.execute(text("SET LOCAL lock_timeout='2s'"))
                    result = capture(connection, args.stage, args.operation, coverage=args.coverage)
                finally:
                    connection.rollback()
        finally:
            engine.dispose()
    else:
        result = compare(json.loads(args.before.read_bytes()), json.loads(args.after.read_bytes()),
                         plan=json.loads(args.plan.read_bytes()) if args.plan else None,
                         expected_plan_sha256=args.expected_plan_sha256, require_coverage=args.require_coverage)
    # The boundary helper durably creates new files. Set restrictive umask first.
    os.umask(0o077)
    boundary.save_new(args.output, result)
    if json.loads(args.output.read_bytes()) != result:
        raise ValueError("receipt readback differs")
    print(json.dumps({"receipt_sha256": file_sha(args.output), "stage": result["stage"],
                      "preservation_passed": result.get("preservation_passed", "capture_only")}))
    return 1 if result.get("gaps") else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"OAG acceptance refused: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
