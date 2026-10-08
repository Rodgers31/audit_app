"""Build a source-bound county cash delta locally; never opens a production DB.

The full actual PDF producer and the existing writer must be replayed first.
Only six new Revenue Receipts sets and their Total coverage provenance may
change. Existing financial values and all other captured images are protected.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from models import BudgetLine, Country, Entity, FiscalPeriod, SourceDocument
from seeding.domains.counties_budget.fetcher import convert_county_pdf_records
from seeding.domains.counties_budget.parser import parse_budget_payload
from seeding.domains.counties_budget import writer
from seeding.pdf_parsers import KENYAN_COUNTIES, CoBQuarterlyReportParser
from seeding.types import DomainRunContext
from seeding.utils import slugify_entity
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

PDF_SHA = "5f5e4f97bbe2752957f284950d0ba90fcff4d47b35fc0ac96a9106ffb59821b3"
# Independently replayed from the pinned935-page PDF (468 records). This
# operation is deliberately bound to that complete output, including all47
# coverage states; callers cannot authorize invented six-county records.
PRODUCER_SHA = "e6df47b5bb143f3ade47c80a6cd0fc15c289b70e21a1b4dbe85d679d0543f65b"
PRODUCER_PAYLOAD_SHA = "d3570dd4d3bf51a5662e19ab952224092820223da0d333ae3056eae2781c112b"
SOURCE_URL = ("https://cob.go.ke/download/county-governments-budget-implementation-"
              "review-report-for-the-financial-year-2025-26/?wpdmdl=16482")
# counties-literal-ok: six source-replayed cash sets approved in round21-closure-validation; exact47-county baseline/payload guards limit the operation.
RECOVERED = {"Bungoma", "Busia", "Kilifi", "Kisii", "Kisumu", "Kitui"}
# counties-literal-ok: four explicit source contradiction/incomplete-cell refusals in the pinned47-county producer coverage; never promoted or ranked.
WITHHELD = {"Kwale", "Migori", "Nyeri", "Samburu"}
MONEY = {"allocated_amount", "actual_spent", "committed_amount"}


@compiles(JSONB, "sqlite")
def _sqlite_json(element, compiler, **kw):
    return "JSON"


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _json(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.name
    raise TypeError(type(value).__name__)


def _load(model, image):
    attrs = {}
    for column in model.__table__.columns:
        if column.name not in image:
            raise ValueError(f"Incomplete {model.__name__} image: {column.name}")
        value = copy.deepcopy(image[column.name])
        if value is not None:
            if column.type.__class__.__name__ == "DateTime":
                value = datetime.fromisoformat(value)
            elif column.name in MONEY:
                _need(type(value) in (int, float, str), "Wrong monetary type")
                value = Decimal(str(value))
            elif column.type.__class__.__name__ == "Enum":
                value = column.type.enum_class[value]
        attrs["meta" if column.name == "metadata" else column.name] = value
    return model(**attrs)


def _image(model, original=None):
    out = copy.deepcopy(original) if original is not None else {}
    for column in model.__table__.columns:
        value = getattr(model, "meta" if column.name == "metadata" else column.name)
        if (original is not None and isinstance(value, datetime)
                and datetime.fromisoformat(original[column.name]) == value):
            continue  # preserve the retained timestamp representation
        if isinstance(value, Decimal):
            value = float(value)
        out[column.name] = json.loads(json.dumps(value, default=_json))
    return out


def _equal(a, b, field):
    if field in MONEY and a is not None and b is not None:
        return Decimal(str(a)) == Decimal(str(b))
    return a == b


def replay_writer(capture, records, stamp):
    """Execute the existing writer on an isolated in-memory copy of full images."""
    engine = create_engine("sqlite://")
    tables = [Country.__table__, Entity.__table__, FiscalPeriod.__table__,
              SourceDocument.__table__, BudgetLine.__table__]
    Country.metadata.create_all(engine, tables=tables)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(stamp).astimezone(tz or timezone.utc)
    try:
        with Session(engine) as session:
            session.add(Country(id=1, iso_code="KEN", name="Kenya", currency="KES",
                                timezone="Africa/Nairobi", default_locale="en"))
            for key, model in [("entities", Entity), ("periods", FiscalPeriod),
                               ("sources", SourceDocument), ("budget_lines", BudgetLine)]:
                session.add_all([_load(model, row) for row in capture[key]])
            session.flush()
            settings = SimpleNamespace(budgets_dataset_url=capture["sources"][0]["url"],
                                       budget_default_currency="KES")
            with patch.object(writer, "datetime", Clock):
                stats = writer.persist_budget_records(
                    session, copy.deepcopy(records), settings,
                    DomainRunContext(since=None, dry_run=True, job_id=None))
                session.flush()
            _need(not stats.errors and not stats.skipped and not stats.superseded,
                  f"Writer refused or removed rows: {stats}")
            originals = {row["id"]: row for row in capture["budget_lines"]}
            lines = [_image(row, originals.get(row.id)) for row in
                     session.scalars(select(BudgetLine).order_by(BudgetLine.id))]
            return lines, vars(stats)
    finally:
        engine.dispose()


def build_plan(capture, raw_records, coverage, stamp):
    normalized_raw = json.loads(json.dumps(raw_records, default=_json))
    producer_payload = json.dumps({"records": normalized_raw, "coverage": coverage},
                                 sort_keys=True, separators=(",", ":"))
    _need(hashlib.sha256(producer_payload.encode()).hexdigest() == PRODUCER_PAYLOAD_SHA,
          "Full producer output is not the independently reviewed pinned PDF replay")
    _need(_digest(ROOT / "backend/seeding/pdf_parsers.py") == PRODUCER_SHA,
          "Producer code changed since reviewed replay")
    _need(capture["schema"] == "round21_county_cash_capture/v1", "Wrong capture schema")
    _need(len(capture["entities"]) == 47 and len(capture["periods"]) == 1
          and len(capture["sources"]) == 1 and not capture["extractions"], "Incomplete cohort")
    for rows, model in [(capture["entities"], Entity), (capture["periods"], FiscalPeriod),
                        (capture["sources"], SourceDocument), (capture["budget_lines"], BudgetLine)]:
        fields = {c.name for c in model.__table__.columns}
        if model is BudgetLine:
            fields.add("validation_warnings")
        for image in rows:
            _need(set(image) == fields, f"Incomplete or extra {model.__name__} fields")
            for key, value in image.items():
                if key == "id" or key.endswith("_id"):
                    _need(value is None or (type(value) is int and value > 0), f"Wrong {key} type")
                if key in MONEY and value is not None:
                    _need(type(value) in (int, float, str) and Decimal(str(value)).is_finite(), "Invalid money")
            _load(model, image)  # execute boundary conversion before any writer replay
    source = capture["sources"][0]
    _need(source["id"] == 2544 and source["publisher"] == "Controller of Budget"
          and source["metadata"]["sha256"] == PDF_SHA
          and source["metadata"]["data_quality"] == "official"
          and source["status"] == "AVAILABLE" and source["doc_type"] == "BUDGET"
          and source["country_id"] == 1 and source["url"] == SOURCE_URL
          and source["title"] == "Controller of Budget County BIRR FY2025/26", "Wrong source binding")
    _need(capture["periods"][0]["id"] == 9 and
          capture["periods"][0]["label"] == "FY2025/26"
          and capture["periods"][0]["country_id"] == 1
          and datetime.fromisoformat(capture["periods"][0]["start_date"]) == datetime(2025,7,1)
          and datetime.fromisoformat(capture["periods"][0]["end_date"]) == datetime(2026,6,30), "Wrong annual period identity/bounds")
    entities = {e["canonical_name"].removesuffix(" County"): e for e in capture["entities"]}
    _need(set(entities) == set(KENYAN_COUNTIES), "Duplicate/missing counties")
    _need(len({e["id"] for e in entities.values()}) == 47, "Duplicate county identities")
    for county, entity in entities.items():
        _need(entity["type"] == "COUNTY" and entity["country_id"] == 1
              and entity["slug"] == slugify_entity(county),
              f"Wrong county type/country/slug identity: {county}")
    _need(set(coverage) == set(KENYAN_COUNTIES), "Incomplete producer coverage")
    _need({c for c, state in coverage.items() if state["status"] == "withheld"} == WITHHELD,
          "Four source conflicts changed")
    _need(all(r["fiscal_year"] == "2025/26" and r["quarter"] is None for r in raw_records),
          "Wrong producer reporting period")
    payload = convert_county_pdf_records(raw_records, source["url"], PDF_SHA)
    records = parse_budget_payload(payload)
    _need(len(records) == len(raw_records), "Conversion dropped producer records")
    before = {r["id"]: r for r in capture["budget_lines"]}
    _need(len(before) == len(capture["budget_lines"]), "Duplicate captured IDs")
    def key(r):
        return (r["entity_id"], r["period_id"], r["category"], r["subcategory"])
    by_key = {key(r): r for r in before.values()}
    _need(len(by_key) == len(before), "Duplicate current budget keys")
    accepted = {r["entity_id"] for r in before.values() if r["category"] == "Revenue Receipts"
                and r["subcategory"] == "Total"}
    expected_accepted = {e["id"] for c, e in entities.items() if c not in RECOVERED | WITHHELD}
    _need(accepted == expected_accepted, "Baseline is not exact37 accepted counties")
    recovered_ids = {entities[c]["id"] for c in RECOVERED}
    _need(not any(r["category"] == "Revenue Receipts" and r["entity_id"] in
                  recovered_ids | {entities[c]["id"] for c in WITHHELD} for r in before.values()),
          "Unexpected receipts already present for six/four")
    # Full producer replay establishes financial equality before a subset is selected.
    full, full_stats = replay_writer(capture, records, stamp)
    full_by_key = {key(r): r for r in full}
    for current in before.values():
        if current["source_document_id"] != source["id"]:
            continue
        _need(key(current) in full_by_key, "Producer lost a linked current row")
        after = full_by_key[key(current)]
        for field in current:
            if field in {"provenance", "created_at"}:
                continue
            _need(_equal(current[field], after[field], field),
                  f"Full producer changes protected {current['id']} {field}")
    subset = [r for r in records if entities[r.entity_name.removesuffix(" County")]["id"]
              in recovered_ids and r.category in {"Total", "Revenue Receipts"}]
    narrow, narrow_stats = replay_writer(capture, subset, stamp)
    updates, inserts = [], []
    for row in narrow:
        if row["id"] not in before:
            _need(row["entity_id"] in recovered_ids and row["category"] == "Revenue Receipts",
                  "Writer added an unapproved row")
            row["created_at"] = datetime.fromisoformat(stamp).replace(tzinfo=None).isoformat()
            row["validation_warnings"] = None
            inserts.append({k: v for k, v in row.items() if k != "id"})
            continue
        old = before[row["id"]]
        changed = {f for f in old if not _equal(old[f], row[f], f)}
        if not changed:
            continue
        _need(row["entity_id"] in recovered_ids and row["category"] == "Total"
              and changed == {"provenance"}, f"Writer changes protected image {row['id']}: {changed}")
        updates.append({"before": old, "after": row})
    _need(len(updates) == 6 and {r["entity_id"] for r in inserts
                               if r["subcategory"] == "Total"} == recovered_ids,
          "Narrow delta must recover six whole cash sets")
    _need(len(narrow) == len(before) + len(inserts), "Writer removed current rows")
    return {"schema": "round21_source_bound_cash_adoption/v1", "production_adopted": False,
            "pdf_sha256": PDF_SHA, "source_id": source["id"], "period_id": 9,
            "recovered_counties": sorted(RECOVERED), "withheld_counties": sorted(WITHHELD),
            "accepted_before": 37, "accepted_after_expected": 43,
            "full_writer_stats": full_stats, "narrow_writer_stats": narrow_stats,
            "updates": updates, "inserts_without_ids": inserts,
            "protected_before": capture, "producer_coverage": coverage,
            "producer_records": normalized_raw, "reviewed_producer_payload_sha256": PRODUCER_PAYLOAD_SHA,
            "sequence_disposition": "Pending root-owned current sequence capture and guarded adoption"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", type=Path, required=True)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--catalog", type=Path, required=True)
    ap.add_argument("--protected-capture", type=Path, required=True)
    ap.add_argument("--trigger-capture", type=Path, required=True)
    args = ap.parse_args()
    _need(_digest(args.pdf) == PDF_SHA, "Wrong PDF bytes")
    producer = CoBQuarterlyReportParser(args.pdf)
    raw = producer.parse()
    _need(_digest(args.pdf) == PDF_SHA, "PDF changed during replay")
    capture = json.loads(args.capture.read_text())
    plan = build_plan(capture, raw, producer.revenue_coverage, capture["completed_utc"])
    plan = bind_catalog(plan, json.loads(args.catalog.read_text()))
    plan = bind_protected(plan, json.loads(args.protected_capture.read_text()), _digest(args.protected_capture))
    plan = bind_triggers(plan, json.loads(args.trigger_capture.read_text()), _digest(args.trigger_capture))
    plan["catalog_sha256"] = _digest(args.catalog)
    plan["capture_sha256"] = _digest(args.capture)
    plan["producer_sha256"] = _digest(ROOT / "backend/seeding/pdf_parsers.py")
    plan["generator_sha256"] = _digest(__file__)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    _need(json.loads(args.output.read_text()) == plan, "Plan readback differs")
    args.output.with_suffix(".adopt.sql").write_text(render_sql(plan))
    args.output.with_suffix(".recover.sql").write_text(render_sql(plan, recovery=True))
    print(f"Prepared {len(plan['inserts'])} cash rows and six coverage updates; no production write")



def bind_catalog(plan, catalog):
    """Reserve explicit IDs locally; adoption must coordinate sequence advance."""
    _need(catalog["schema"] == "round21_cash_catalog/v1" and
          not catalog["other_source_lines"], "Unreviewed source periods")
    maximum, sequence = catalog["budget_max"][0], catalog["budget_sequence"][0]
    _need(maximum["sequence"] == "public.budget_lines_id_seq", "Wrong owned sequence")
    _need(type(maximum["max_id"]) is int and type(sequence["last_value"]) is int
          and type(sequence["is_called"]) is bool, "Malformed sequence image")
    expected = {c.name for c in BudgetLine.__table__.columns} | {"validation_warnings"}
    _need({c["column_name"] for c in catalog["columns"]} == expected
          and len(catalog["columns"]) == len(expected), "Budget column catalogue changed")
    _need(all(set(r) == {"name", "kind", "definition", "from_table", "to_table"}
              for r in catalog["constraints"]), "Malformed constraint catalogue")
    out = copy.deepcopy(plan)
    start = max(maximum["max_id"], sequence["last_value"])
    out["inserts"] = [dict(r, id=start + i + 1) for i, r in
                      enumerate(out.pop("inserts_without_ids"))]
    out["catalog"] = copy.deepcopy(catalog)
    out["sequence_disposition"] = {
        "before": sequence, "after_commit_required": {"last_value": start + len(out["inserts"]),
        "is_called": True}, "default_rollback_changes_sequence": False,
        "commit_sequence_owner": "root; advance while writer locks held; retain durable receipt"}
    return out


def render_sql(plan, recovery=False):
    """Return exact-image guarded PostgreSQL SQL that ends in ROLLBACK.

    No nextval/setval is issued. Root must coordinate sequence advance for an
    explicitly authorized commit; recovery leaves sequence monotonic.
    """
    expected = bind_catalog(build_plan(plan["protected_before"], plan["producer_records"],
        plan["producer_coverage"], plan["protected_before"]["completed_utc"]), plan["catalog"])
    for key in ("updates", "inserts", "recovered_counties", "withheld_counties", "source_id",
                "period_id", "pdf_sha256", "accepted_before", "accepted_after_expected",
                "reviewed_producer_payload_sha256", "sequence_disposition"):
        _need(json.dumps(plan[key], sort_keys=True, separators=(",", ":")) ==
              json.dumps(expected[key], sort_keys=True, separators=(",", ":")), f"Plan was altered after producer derivation: {key}")
    bind_protected(plan, {"protected": plan["protected_totals"],
                         **plan["protected_capture_context"]},
                   plan["protected_capture_context"]["sha256"])
    bind_triggers(plan, {"schema": "round21_budget_triggers/v1", "triggers": plan["triggers"]},
                  plan["trigger_capture_sha256"])
    c = plan["protected_before"]
    cat = plan["catalog"]
    incoming = c["budget_lines"]
    after = {r["id"]: copy.deepcopy(r) for r in incoming}
    for pair in plan["updates"]:
        _need(pair["before"] == after[pair["before"]["id"]], "Update before-image mismatch")
        _need({k for k in pair["before"] if pair["before"][k] != pair["after"][k]}
              == {"provenance"}, "Update changes a protected field")
        after[pair["before"]["id"]] = pair["after"]
    after.update({r["id"]: r for r in plan["inserts"]})
    payload = {"before": c, "after_lines": list(after.values()), "catalog": cat,
               "updates": plan["updates"], "inserts": plan["inserts"],
               "protected": plan["protected_totals"], "triggers": plan["triggers"]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    _need("$cash$" not in encoded, "Unsafe SQL literal delimiter")
    expected_lines = "after_lines" if recovery else "before,budget_lines"
    target_lines = "before,budget_lines" if recovery else "after_lines"
    count_before = cat["budget_max"][0]["rows"] + (len(plan["inserts"]) if recovery else 0)
    max_before = max(r["id"] for r in plan["inserts"]) if recovery else cat["budget_max"][0]["max_id"]
    sequence_guard = """
 IF (SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)
     FROM public.budget_lines_id_seq) NOT IN ((p#>'{catalog,budget_sequence,0}') - 'log_cnt',
      jsonb_build_object('last_value',(SELECT max((x->>'id')::int) FROM jsonb_array_elements(p->'inserts') x),
                         'is_called',true))
 THEN RAISE EXCEPTION 'Cash sequence drift prevents recovery'; END IF;
""" if recovery else """
 IF (SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)
     FROM public.budget_lines_id_seq) IS DISTINCT FROM (p#>'{catalog,budget_sequence,0}') - 'log_cnt'
 THEN RAISE EXCEPTION 'Cash sequence drift'; END IF;"""
    mutation = """
 IF EXISTS (SELECT 1 FROM public.annotations
   WHERE ref_type='budget_line' AND ref_id IN (SELECT (x->>'id')::int FROM jsonb_array_elements(p->'inserts') x))
 THEN RAISE EXCEPTION 'New annotation dependency prevents recovery'; END IF;
 DELETE FROM public.budget_lines WHERE id IN (SELECT (x->>'id')::int FROM jsonb_array_elements(p->'inserts') x);
 UPDATE public.budget_lines b SET provenance = x#>'{before,provenance}'
 FROM jsonb_array_elements(p->'updates') x WHERE b.id=(x#>>'{before,id}')::int;
""" if recovery else """
 INSERT INTO public.budget_lines SELECT * FROM jsonb_populate_recordset(NULL::public.budget_lines, p->'inserts');
 UPDATE public.budget_lines b SET provenance = x#>'{after,provenance}'
 FROM jsonb_array_elements(p->'updates') x WHERE b.id=(x#>>'{before,id}')::int;
"""
    protected_checks = []
    stable_checks = []
    for table in PROTECTED_TABLES:
        if recovery and table == "budget_lines":
            continue
        check = f"""
 SELECT {proof_expression(table, cte=True)} INTO observed FROM public.{table} {table};
 IF observed IS DISTINCT FROM p#>'{{protected,{table}}}' THEN
 RAISE EXCEPTION 'Cash protected whole table drift: {table}'; END IF;"""
        protected_checks.append(check)
        if table != 'budget_lines':
            stable_checks.append(check)
    protected_guard = "\n".join(protected_checks)
    stable_guard = "\n".join(stable_checks)
    # Derive canonical typed rows from the guarded current whole table. This
    # retains every unrelated image without copying all of them into the plan.
    projection = """
 SELECT (jsonb_populate_record(NULL::public.budget_lines,
 COALESCE(x#>'{before}',to_jsonb(b)))).* FROM public.budget_lines b
 LEFT JOIN jsonb_array_elements(p->'updates') x ON b.id=(x#>>'{before,id}')::int
 WHERE b.id NOT IN (SELECT (v->>'id')::int FROM jsonb_array_elements(p->'inserts') v)
""" if recovery else """
 SELECT (jsonb_populate_record(NULL::public.budget_lines,
 COALESCE(x#>'{after}',to_jsonb(b)))).* FROM public.budget_lines b
 LEFT JOIN jsonb_array_elements(p->'updates') x ON b.id=(x#>>'{before,id}')::int
 UNION ALL SELECT * FROM jsonb_populate_recordset(NULL::public.budget_lines,p->'inserts')
"""
    projection_sql = f"SELECT {proof_expression('projected', cte=True)} INTO projected_proof FROM ({projection}) projected;"
    inverse_projection_guard = """
 IF projected_proof IS DISTINCT FROM p#>'{protected,budget_lines}' THEN
 RAISE EXCEPTION 'Cash unrelated budget image drift prevents recovery'; END IF;
""" if recovery else ""
    locks = ", ".join("public." + t for t in sorted(set(PROTECTED_TABLES) | {"annotations", "ingestion_jobs", "fiscal_periods"}))
    return f"""-- Source-bound county cash {'recovery' if recovery else 'adoption'} rehearsal; default ROLLBACK.
-- Explicit IDs do not consume the sequence. Commit requires root-owned locked sequence coordination.
BEGIN ISOLATION LEVEL READ COMMITTED;
SET LOCAL lock_timeout='5s';
SET LOCAL statement_timeout='30s';
LOCK TABLE {locks} IN SHARE ROW EXCLUSIVE MODE;
DO $guard$
DECLARE p jsonb := $cash${encoded}$cash$::jsonb; observed jsonb; projected_proof jsonb; sequence_before jsonb;
BEGIN
 {protected_guard}
 IF (SELECT jsonb_agg(to_jsonb(z) ORDER BY ordinal_position) FROM information_schema.columns z
     WHERE table_schema='public' AND table_name='budget_lines') IS DISTINCT FROM p#>'{{catalog,columns}}'
 THEN RAISE EXCEPTION 'Cash column catalogue drift'; END IF;
 SELECT jsonb_agg(jsonb_build_object('name',conname,'kind',contype::text,
 'definition',pg_get_constraintdef(oid),'from_table',conrelid::regclass::text,
 'to_table',CASE WHEN confrelid=0 THEN NULL ELSE confrelid::regclass::text END) ORDER BY conname)
 INTO observed FROM pg_constraint WHERE conrelid='public.budget_lines'::regclass
 OR confrelid='public.budget_lines'::regclass;
 IF observed IS DISTINCT FROM p#>'{{catalog,constraints}}' THEN RAISE EXCEPTION 'Cash constraint catalogue drift'; END IF;
 IF (SELECT count(*) FROM public.budget_lines) IS DISTINCT FROM {count_before}
 OR (SELECT max(id) FROM public.budget_lines) IS DISTINCT FROM {max_before}
 THEN RAISE EXCEPTION 'Cash global budget count/max drift'; END IF;
 {sequence_guard}
 SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)
 INTO sequence_before FROM public.budget_lines_id_seq;
 IF EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid='public.budget_lines'::regclass
            AND NOT tgisinternal) THEN
 RAISE EXCEPTION 'Unreviewed BudgetLine trigger prevents scoped cash adoption/recovery'; END IF;
 SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled::text,
 'internal',t.tgisinternal,'definition',pg_get_triggerdef(t.oid),
 'function_schema',n.nspname,'function_name',f.proname,'function_definition',NULL) ORDER BY t.tgname)
 INTO observed FROM pg_trigger t JOIN pg_proc f ON f.oid=t.tgfoid
 JOIN pg_namespace n ON n.oid=f.pronamespace WHERE t.tgrelid='public.budget_lines'::regclass;
 IF observed IS DISTINCT FROM p->'triggers' THEN RAISE EXCEPTION 'Cash trigger catalogue drift'; END IF;
 SELECT jsonb_agg(to_jsonb(b) ORDER BY id) INTO observed FROM public.budget_lines b
 WHERE period_id=9 AND entity_id IN (SELECT (x->>'id')::int FROM jsonb_array_elements(p#>'{{before,entities}}') x);
 IF observed IS DISTINCT FROM (SELECT jsonb_agg(x ORDER BY (x->>'id')::int)
 FROM jsonb_array_elements(p#>'{{{expected_lines}}}') x)
 THEN RAISE EXCEPTION 'Cash whole budget cohort drift'; END IF;
 SELECT jsonb_agg(to_jsonb(e) ORDER BY id) INTO observed FROM public.entities e
 WHERE id IN (SELECT (x->>'id')::int FROM jsonb_array_elements(p#>'{{before,entities}}') x);
 IF observed IS DISTINCT FROM (SELECT jsonb_agg(x ORDER BY (x->>'id')::int) FROM jsonb_array_elements(p#>'{{before,entities}}') x)
 THEN RAISE EXCEPTION 'Cash whole entity image drift'; END IF;
 IF (SELECT to_jsonb(s) FROM public.source_documents s WHERE id=2544) IS DISTINCT FROM p#>'{{before,sources,0}}'
 OR (SELECT to_jsonb(f) FROM public.fiscal_periods f WHERE id=9) IS DISTINCT FROM p#>'{{before,periods,0}}'
 THEN RAISE EXCEPTION 'Cash source/period drift'; END IF;
 IF (SELECT to_jsonb(j) FROM public.ingestion_jobs j WHERE id=3157) IS DISTINCT FROM p#>'{{before,job3157,0}}'
 THEN RAISE EXCEPTION 'Cash historical job drift'; END IF;
 IF EXISTS (SELECT 1 FROM public.budget_lines WHERE source_document_id=2544 AND period_id<>9)
 OR EXISTS (SELECT 1 FROM public.extractions WHERE source_document_id=2544)
 THEN RAISE EXCEPTION 'Cash unreviewed source cohort'; END IF;
 {projection_sql}
 {inverse_projection_guard}
 {mutation}
 SELECT {proof_expression("budget_lines", cte=True)} INTO observed FROM public.budget_lines budget_lines;
 IF observed IS DISTINCT FROM projected_proof THEN RAISE EXCEPTION 'Cash whole budget postimage proof mismatch'; END IF;
 {stable_guard}
 IF (SELECT to_jsonb(s) FROM public.source_documents s WHERE id=2544) IS DISTINCT FROM p#>'{{before,sources,0}}'
 OR (SELECT to_jsonb(f) FROM public.fiscal_periods f WHERE id=9) IS DISTINCT FROM p#>'{{before,periods,0}}'
 THEN RAISE EXCEPTION 'Cash source/period postimage drift'; END IF;
 IF (SELECT to_jsonb(j) FROM public.ingestion_jobs j WHERE id=3157) IS DISTINCT FROM p#>'{{before,job3157,0}}'
 THEN RAISE EXCEPTION 'Cash historical job postimage drift'; END IF;
 IF (SELECT jsonb_build_object('last_value',last_value,'is_called',is_called)
 FROM public.budget_lines_id_seq) IS DISTINCT FROM sequence_before
 THEN RAISE EXCEPTION 'Cash sequence postimage drift; preserve external advance'; END IF;
 SELECT jsonb_agg(to_jsonb(b) ORDER BY id) INTO observed FROM public.budget_lines b
 WHERE period_id=9 AND entity_id IN (SELECT (x->>'id')::int FROM jsonb_array_elements(p#>'{{before,entities}}') x);
 IF observed IS DISTINCT FROM (SELECT jsonb_agg(x ORDER BY (x->>'id')::int)
 FROM jsonb_array_elements(p#>'{{{target_lines}}}') x)
 THEN RAISE EXCEPTION 'Cash postimage mismatch'; END IF;
 RAISE NOTICE 'Source-bound cash {'inverse' if recovery else 'delta'} verified; transaction defaults to rollback';
END $guard$;
ROLLBACK;
"""


PROTECTED_TABLES = ("audits", "budget_lines", "debt_instruments", "debt_timeline",
    "economic_indicators", "entities", "extractions", "fiscal_summaries", "gdp_data",
    "loans", "parliament_source_documents", "population_data", "poverty_indices",
    "revenue_by_source", "source_documents")


def proof_expression(table, cte=False):
    # PostgreSQL's typed to_jsonb text, framed by length, matches root capture.
    name = table if cte else "public." + table
    return ("jsonb_build_object('count',count(*),'sha256',encode(sha256(convert_to("
        "coalesce(string_agg(length(to_jsonb(" + table + ")::text)::text||':'||"
        "to_jsonb(" + table + ")::text,'' ORDER BY " + table + ".id),''),'UTF8')),'hex'))"
        + ("" if cte else " FROM " + name + " " + table))


def bind_protected(plan, capture, capture_sha256):
    totals = capture["protected"]
    _need(set(totals) == set(PROTECTED_TABLES), "Incomplete protected15 table scope")
    for table, proof in totals.items():
        _need(set(proof) == {"count", "sha256"} and type(proof["count"]) is int
              and proof["count"] >= 0 and isinstance(proof["sha256"], str)
              and len(proof["sha256"]) == 64 and
              all(x in "0123456789abcdef" for x in proof["sha256"]),
              f"Malformed protected proof: {table}")
    _need(totals["budget_lines"]["count"] == plan["catalog"]["budget_max"][0]["rows"],
          "Protected budget count disagrees with current catalogue")
    out = copy.deepcopy(plan)
    out["protected_totals"] = copy.deepcopy(totals)
    out["protected_capture_context"] = {"sha256": capture_sha256,
        "schema": capture["schema"], "started_utc": capture["started_utc"],
        "completed_utc": capture["completed_utc"]}
    return out


def bind_triggers(plan, capture, capture_sha256):
    _need(capture["schema"] == "round21_budget_triggers/v1", "Wrong trigger capture")
    rows = capture["triggers"]
    _need(len(rows) == 8 and len({r["name"] for r in rows}) == 8, "Incomplete internal FK trigger capture")
    for row in rows:
        _need(set(row) == {"name", "enabled", "internal", "definition", "function_schema",
                           "function_name", "function_definition"}
              and type(row["internal"]) is bool and row["internal"]
              and row["enabled"] == "O" and row["function_schema"] == "pg_catalog"
              and row["function_name"] in {"RI_FKey_check_ins", "RI_FKey_check_upd"}
              and row["function_definition"] is None, "Unreviewed BudgetLine trigger")
    out = copy.deepcopy(plan)
    out["triggers"] = copy.deepcopy(rows)
    out["trigger_capture_sha256"] = capture_sha256
    return out


if __name__ == "__main__":
    main()
