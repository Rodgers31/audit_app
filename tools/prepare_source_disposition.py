"""Render exact, rollback-default source1707/1718 disposition and inverse.

Offline only: no credentials, database connection, or execution entry point.
The original dated source packet is provenance evidence, not an input accepted
by this renderer. A release owner supplies a fresh complete guarded capture.
"""

import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path


SOURCE_FIELDS = {
    "id",
    "country_id",
    "publisher",
    "title",
    "url",
    "file_path",
    "fetch_date",
    "md5",
    "doc_type",
    "status",
    "content_type",
    "http_status",
    "last_verified_at",
    "last_seen_at",
    "metadata",
    "created_at",
}
REFERENCE_TABLES = {
    "audits",
    "budget_lines",
    "debt_instruments",
    "debt_timeline",
    "economic_indicators",
    "extractions",
    "fiscal_summaries",
    "gdp_data",
    "loans",
    "parliament_source_documents",
    "population_data",
    "poverty_indices",
    "revenue_by_source",
}
CLASSIFICATIONS = {1707: "test_fixture", 1718: "modelled_estimate"}
PUBLISHERS = {1707: "AuditGava (test fixture)", 1718: "AuditGava (modelled estimate)"}
HISTORY = "ec7706c8395d8ccf4dc86e9a9af7a1c0d9cc0777"
GENERATED_LABEL = "Estimated based on CRA Equitable Share FY 2023/24"
LOGICAL_COLUMNS = {
    ("admin_audit_log", "payload"),
    ("audits", "provenance"),
    ("audits", "validation_warnings"),
    ("budget_lines", "provenance"),
    ("budget_lines", "validation_warnings"),
    ("countries", "metadata"),
    ("debt_instruments", "metadata"),
    ("debt_timeline", "metadata"),
    ("economic_indicators", "metadata"),
    ("entities", "alt_names"),
    ("entities", "metadata"),
    ("extractions", "extracted_json"),
    ("fiscal_summaries", "metadata"),
    ("gdp_data", "metadata"),
    ("ingestion_jobs", "errors"),
    ("ingestion_jobs", "metadata"),
    ("loans", "provenance"),
    ("newsletter_subscribers", "metadata"),
    ("parliament_source_documents", "metadata"),
    ("population_data", "metadata"),
    ("poverty_indices", "metadata"),
    ("quick_questions", "tags"),
    ("revenue_by_source", "metadata"),
    ("source_documents", "metadata"),
    ("users", "roles"),
    ("validation_failures", "validation_errors"),
    ("validation_failures", "validation_warnings"),
    ("validation_failures", "raw_data"),
    ("validation_failures", "metadata"),
    ("watchlist_items", "metadata"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def timestamp(value, field, nullable=False):
    if value is None and nullable:
        return
    require(
        isinstance(value, str)
        and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?",
            value,
        )
        is not None,
        f"{field} must be a complete timestamp",
    )
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} must be a valid timestamp") from None


def source_field_types(source):
    for field in ("publisher", "title", "url", "doc_type", "status"):
        require(isinstance(source[field], str), f"{field} must be text")
    for field in ("file_path", "content_type"):
        require(
            source[field] is None or isinstance(source[field], str),
            f"{field} must be nullable text",
        )
    require(
        source["md5"] is None
        or (
            isinstance(source["md5"], str)
            and re.fullmatch(r"[0-9a-fA-F]{32}", source["md5"]) is not None
        ),
        "md5 must be a nullable 32-digit hexadecimal digest",
    )
    require(
        source["http_status"] is None
        or (type(source["http_status"]) is int and 100 <= source["http_status"] <= 599),
        "http_status must be a nullable integer HTTP status",
    )
    for field in ("fetch_date", "last_seen_at", "created_at"):
        timestamp(source[field], field)
    timestamp(source["last_verified_at"], "last_verified_at", nullable=True)


def proposal(capture):
    require(isinstance(capture, dict), "capture must be an object")
    require(
        capture.get("schema") == "source_disposition_capture/v1",
        "fresh capture schema required",
    )
    require(
        isinstance(capture.get("captured_utc"), str) and capture["captured_utc"],
        "capture time required",
    )
    sources = capture.get("sources")
    require(
        isinstance(sources, list) and len(sources) == 2,
        "exactly two source images required",
    )
    require(
        all(isinstance(s, dict) and set(s) == SOURCE_FIELDS for s in sources),
        "complete source images required",
    )
    require(
        all(type(s["id"]) is int for s in sources)
        and {s["id"] for s in sources} == {1707, 1718},
        "exact source IDs required",
    )
    by_id = {s["id"]: s for s in sources}
    for source_id, s in by_id.items():
        source_field_types(s)
        require(
            type(s["country_id"]) is int and s["country_id"] == 1,
            "Kenyan source identity required",
        )
        require(
            s["publisher"] == "Controller of Budget"
            and s["status"] == "AVAILABLE"
            and s["doc_type"] == "BUDGET",
            "source classification drift",
        )
        require(isinstance(s["metadata"], dict), "metadata object required")
        require(
            "source_classification" not in s["metadata"]
            and "disposition" not in s["metadata"],
            "existing disposition requires fresh review",
        )
    require(
        by_id[1707]["url"] == "https://fixtures.example/budgets"
        and by_id[1707]["metadata"].get("dataset_id") == "fixture-budgets"
        and by_id[1707]["title"] == "County Budget Execution Summary",
        "1707 fixture origin drift",
    )
    require(
        by_id[1718]["url"] == "https://www.crakenya.org/county-allocations/"
        and by_id[1718]["metadata"].get("data_quality") == "estimated"
        and by_id[1718]["metadata"].get("source_label") == GENERATED_LABEL
        and by_id[1718]["title"] == GENERATED_LABEL,
        "1718 generated origin drift",
    )
    references = capture.get("source_references")
    require(
        isinstance(references, list) and len(references) == len(REFERENCE_TABLES),
        "complete reference capture required",
    )
    require(
        all(
            isinstance(r, dict)
            and set(r) == {"table", "column", "rows"}
            and r["column"] == "source_document_id"
            and r["rows"] == []
            for r in references
        ),
        "nonempty or malformed dependencies require separate review",
    )
    require(
        {r["table"] for r in references} == REFERENCE_TABLES,
        "reference table coverage drift",
    )
    require(
        capture.get("logical_matches") == [], "logical matches require separate review"
    )
    logical_columns = capture.get("logical_scan_columns")
    require(
        isinstance(logical_columns, list)
        and len(logical_columns) == len(LOGICAL_COLUMNS),
        "complete logical column catalogue required",
    )
    require(
        all(
            isinstance(c, dict)
            and set(c) == {"table", "column"}
            and isinstance(c["table"], str)
            and isinstance(c["column"], str)
            for c in logical_columns
        ),
        "logical column catalogue shape drift",
    )
    require(
        {(c["table"], c["column"]) for c in logical_columns} == LOGICAL_COLUMNS,
        "logical column catalogue coverage drift",
    )
    fks = capture.get("foreign_keys")
    require(isinstance(fks, list), "foreign key capture required")
    incoming = [
        f
        for f in fks
        if isinstance(f, dict) and f.get("to_table") == "source_documents"
    ]
    require(
        len(incoming) == 13
        and {f.get("from_table") for f in incoming} == REFERENCE_TABLES,
        "incoming source FK coverage drift",
    )
    for f in incoming:
        require(
            set(f) == {"conname", "definition", "from_table", "to_table"},
            "FK shape drift",
        )
        require(
            all(isinstance(v, str) and v for v in f.values()), "malformed FK identity"
        )
        require(
            re.fullmatch(
                r"FOREIGN KEY \(source_document_id\) REFERENCES source_documents\(id\)( ON DELETE SET NULL)?",
                f["definition"],
            )
            is not None,
            "unexpected source FK definition",
        )
    require(len({f["conname"] for f in incoming}) == 13, "duplicate source FK identity")
    changes = []
    for source_id in (1707, 1718):
        before = copy.deepcopy(by_id[source_id])
        after = copy.deepcopy(before)
        after["publisher"] = PUBLISHERS[source_id]
        after["status"] = "ARCHIVED"
        after["metadata"]["source_classification"] = CLASSIFICATIONS[source_id]
        after["metadata"]["disposition"] = {
            "issue": 319,
            "reason": "Retained app artefact; excluded from public publisher inventory.",
            "historical_git_commit": HISTORY,
            "original_publisher": before["publisher"],
            "original_status": before["status"],
        }
        changes.append({"id": source_id, "before": before, "after": after})
    # Encode before returning: nonfinite/unserializable inputs cannot become SQL.
    json.dumps(capture, allow_nan=False)
    return {
        "schema": "source_disposition_plan/v1",
        "captured_utc": capture["captured_utc"],
        "capture_canonical_sha256": hashlib.sha256(
            json.dumps(
                capture,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ).encode()
        ).hexdigest(),
        "changes": changes,
        "foreign_keys": sorted(incoming, key=lambda f: f["conname"]),
        "logical_scan_columns": sorted(
            logical_columns, key=lambda c: (c["table"], c["column"])
        ),
    }


def render(capture):
    plan = proposal(capture)
    payload = json.dumps(plan, sort_keys=True, ensure_ascii=False, allow_nan=False)
    tag = "$source_disposition_319$"
    require(tag not in payload, "unsafe SQL delimiter")
    preamble = f"""-- REVIEW ONLY. Root refreshes/approves inputs and prerequisites. Default ROLLBACK.
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE TEMP TABLE source_disposition_plan(payload jsonb) ON COMMIT DROP;
INSERT INTO source_disposition_plan VALUES ({tag}{payload}{tag}::jsonb);
-- Coordinated writer window required. Lock every public table inspected by the
-- logical-reference guard, so new JSON references cannot enter during review.
DO $guard$ DECLARE t record; BEGIN
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LOOP
  EXECUTE format('LOCK TABLE public.%I IN SHARE ROW EXCLUSIVE MODE', t.tablename);
 END LOOP;
END $guard$;
CREATE TEMP VIEW disposition_changes AS SELECT x FROM source_disposition_plan, jsonb_array_elements(payload->'changes') x;
CREATE FUNCTION pg_temp.disposition_logical_ref(v jsonb, key text DEFAULT '') RETURNS boolean LANGUAGE plpgsql AS $guard$
DECLARE item record; child jsonb; scalar text;
BEGIN
 IF jsonb_typeof(v)='object' THEN
  FOR item IN SELECT * FROM jsonb_each(v) LOOP
   IF pg_temp.disposition_logical_ref(item.value, item.key) THEN RETURN true; END IF;
  END LOOP;
 ELSIF jsonb_typeof(v)='array' THEN
  FOR child IN SELECT * FROM jsonb_array_elements(v) LOOP
   IF pg_temp.disposition_logical_ref(child, key) THEN RETURN true; END IF;
  END LOOP;
 ELSIF jsonb_typeof(v) IN ('number','string') THEN
  scalar := btrim(v #>> '{{}}');
  IF key IN ('source_document_id','source_document_ids','source_id','document_id','doc_id') AND scalar ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN
   IF scalar::numeric IN (1707,1718) THEN RETURN true; END IF;
  END IF;
  IF jsonb_typeof(v)='string' AND (position('https://fixtures.example/budgets' IN scalar)>0 OR position('https://www.crakenya.org/county-allocations/' IN scalar)>0) THEN RETURN true; END IF;
 END IF;
 RETURN false;
END $guard$;
DO $guard$ DECLARE actual jsonb; t record; found boolean; BEGIN
 SELECT coalesce(jsonb_agg(jsonb_build_object('table',table_name,'column',column_name) ORDER BY table_name,column_name),'[]'::jsonb) INTO actual FROM information_schema.columns WHERE table_schema='public' AND data_type IN ('json','jsonb');
 IF actual IS DISTINCT FROM (SELECT payload->'logical_scan_columns' FROM source_disposition_plan) THEN RAISE EXCEPTION 'Logical column catalogue drift'; END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace WHERE c.contype='f' AND c.confrelid='public.source_documents'::regclass AND n.nspname<>'public') THEN RAISE EXCEPTION 'Source FK outside reviewed public scope'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('conname',c.conname,'definition',pg_get_constraintdef(c.oid),'from_table',cl.relname,'to_table','source_documents') ORDER BY c.conname), '[]'::jsonb)
 INTO actual FROM pg_constraint c JOIN pg_class cl ON cl.oid=c.conrelid JOIN pg_namespace n ON n.oid=cl.relnamespace
 WHERE c.contype='f' AND c.confrelid='public.source_documents'::regclass AND n.nspname='public';
 IF actual IS DISTINCT FROM (SELECT payload->'foreign_keys' FROM source_disposition_plan) THEN RAISE EXCEPTION 'Source FK catalogue drift'; END IF;
 FOR t IN SELECT table_schema,table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND column_name='source_document_id' LOOP
  EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I WHERE %I IN (1707,1718))',t.table_schema,t.table_name,t.column_name) INTO found;
  IF found THEN RAISE EXCEPTION 'Source dependency present: %',t.table_name; END IF;
 END LOOP;
 FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename LOOP
  IF t.tablename='source_documents' THEN
   EXECUTE 'SELECT EXISTS(SELECT 1 FROM public.source_documents d WHERE d.id NOT IN (1707,1718) AND pg_temp.disposition_logical_ref(to_jsonb(d)))' INTO found;
  ELSE
   EXECUTE format('SELECT EXISTS(SELECT 1 FROM public.%I d WHERE pg_temp.disposition_logical_ref(to_jsonb(d)))',t.tablename) INTO found;
  END IF;
  IF found THEN RAISE EXCEPTION 'Logical source reference present: %',t.tablename; END IF;
 END LOOP;
END $guard$;
"""

    def operation(expected, replacement):
        return (
            preamble
            + f"""DO $guard$ BEGIN
 IF EXISTS(SELECT 1 FROM disposition_changes p LEFT JOIN public.source_documents d ON d.id=(p.x->>'id')::int WHERE d.id IS NULL OR to_jsonb(d) IS DISTINCT FROM p.x->'{expected}') THEN
  RAISE EXCEPTION 'Complete source before-image drift: refresh and review';
 END IF;
END $guard$;
UPDATE public.source_documents d SET
 publisher=p.x->'{replacement}'->>'publisher',
 status=(jsonb_populate_record(NULL::public.source_documents,p.x->'{replacement}')).status,
 metadata=p.x->'{replacement}'->'metadata'
FROM disposition_changes p WHERE d.id=(p.x->>'id')::int RETURNING d.id;
DO $guard$ BEGIN
 IF EXISTS(SELECT 1 FROM disposition_changes p LEFT JOIN public.source_documents d ON d.id=(p.x->>'id')::int WHERE d.id IS NULL OR to_jsonb(d) IS DISTINCT FROM p.x->'{replacement}') THEN
  RAISE EXCEPTION 'Complete source after-image mismatch';
 END IF;
END $guard$;
-- Review exact returned IDs1707/1718; all other row columns retained.
ROLLBACK;
"""
        )

    return plan, operation("before", "after"), operation("after", "before")


if __name__ == "__main__":
    capture = json.loads(Path(sys.argv[1]).read_text())
    plan, forward, inverse = render(capture)
    destination = Path(sys.argv[2])
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "plan.json").write_text(
        json.dumps(plan, sort_keys=True, indent=2) + "\n"
    )
    (destination / "archive.sql").write_text(forward)
    (destination / "recover.sql").write_text(inverse)
    print(f"Review packet written to {destination}; both scripts end in ROLLBACK.")
