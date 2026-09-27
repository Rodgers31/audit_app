"""Render review-only SQL; never connects to a database or applies changes.

Usage: python tools/prepare_legacy_evidence_cleanup.py manifest.json output_dir
Both scripts end in ROLLBACK. Release owner must refresh/approve the exact
manifest, take a backup and review any drift before an authorized execution.
"""
import json
import sys
from pathlib import Path


def render(manifest):
    entities = manifest["entities"]
    audits = manifest["delete_audits"]
    if len({e["id"] for e in entities}) != len(entities) or len(
        {a["id"] for a in audits}
    ) != len(audits):
        raise ValueError("duplicate row ids")
    for e in entities:
        assert e["after"] == {
            k: v for k, v in e["before"].items() if k not in e["remove_keys"]
        }
    for a in audits:
        assert (
            a["source_document_id"] == 1836
            and a["extraction_id"] is None
            and a["page_ref"] is None
        )
    document = manifest["retired_source_document"]
    if (
        document["id"] != 1836
        or document["metadata"].get("source") != "oag_national_audit_data.json"
    ):
        raise ValueError("unexpected retired fixture provenance")
    if manifest["referencing_constraints"] != []:
        raise ValueError("audit references require a separately reviewed plan")
    payload = json.dumps(
        {"entities": entities, "audits": audits, "document": document},
        ensure_ascii=False,
    )
    delimiter = "$auditgava_review_20260927$"
    if delimiter in payload:
        raise ValueError("unsafe SQL delimiter in snapshot")
    preamble = f"""-- REVIEW ONLY. No automatic execution or migration hook. Ends in ROLLBACK.
BEGIN;
SET LOCAL lock_timeout = '5s';
LOCK TABLE entities, audits, source_documents IN SHARE ROW EXCLUSIVE MODE;
CREATE TEMP TABLE evidence_cleanup_plan(payload jsonb) ON COMMIT DROP;
INSERT INTO evidence_cleanup_plan VALUES ({delimiter}{payload}{delimiter}::jsonb);
CREATE TEMP VIEW entity_plan AS SELECT x FROM evidence_cleanup_plan, jsonb_array_elements(payload->'entities') x;
CREATE TEMP VIEW audit_plan AS SELECT x FROM evidence_cleanup_plan, jsonb_array_elements(payload->'audits') x;
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM source_documents d, evidence_cleanup_plan p WHERE d.id=1836 AND to_jsonb(d)=p.payload->'document') THEN
  RAISE EXCEPTION 'Retired source document drift: refresh provenance and review again';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_constraint WHERE contype='f' AND confrelid='audits'::regclass) THEN
  RAISE EXCEPTION 'Audit references changed: review relationships before cleanup or recovery';
 END IF;
END $$;
"""
    forward = (
        preamble
        + """DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM entity_plan p LEFT JOIN entities e ON e.id=(p.x->>'id')::int WHERE e.id IS NULL OR e.metadata IS DISTINCT FROM p.x->'before' OR e.canonical_name IS DISTINCT FROM p.x->>'canonical_name') THEN
  RAISE EXCEPTION 'Entity snapshot drift: refresh manifest and review again';
 END IF;
 IF EXISTS(SELECT 1 FROM audit_plan p LEFT JOIN audits a ON a.id=(p.x->>'id')::int WHERE a.id IS NULL OR to_jsonb(a) IS DISTINCT FROM p.x) THEN
  RAISE EXCEPTION 'Audit snapshot drift: refresh manifest and review again';
 END IF;
 IF (SELECT count(*) FROM audits WHERE source_document_id=1836) <> (SELECT count(*) FROM audit_plan) THEN
  RAISE EXCEPTION 'Document 1836 coverage changed';
 END IF;
END $$;
UPDATE entities e SET metadata=p.x->'after' FROM entity_plan p WHERE e.id=(p.x->>'id')::int RETURNING e.id;
DELETE FROM audits a USING audit_plan p WHERE a.id=(p.x->>'id')::int RETURNING a.id;
-- Review returned IDs; no changes to source documents or other #319 items.
ROLLBACK;
"""
    )
    recovery = (
        preamble
        + """DO $$ BEGIN
 IF EXISTS(SELECT 1 FROM entity_plan p LEFT JOIN entities e ON e.id=(p.x->>'id')::int WHERE e.id IS NULL OR e.metadata IS DISTINCT FROM p.x->'after') THEN
  RAISE EXCEPTION 'Post-cleanup entity drift: do not overwrite newer data';
 END IF;
 IF EXISTS(SELECT 1 FROM audit_plan p JOIN audits a ON a.id=(p.x->>'id')::int) THEN
  RAISE EXCEPTION 'Audit IDs occupied: reconcile manually';
 END IF;
END $$;
UPDATE entities e SET metadata=p.x->'before' FROM entity_plan p WHERE e.id=(p.x->>'id')::int RETURNING e.id;
INSERT INTO audits SELECT (jsonb_populate_record(NULL::audits, p.x)).* FROM audit_plan p RETURNING id;
-- IDs were already allocated; do not reset the sequence backwards.
ROLLBACK;
"""
    )
    return forward, recovery


if __name__ == "__main__":
    manifest = json.loads(Path(sys.argv[1]).read_text())
    destination = Path(sys.argv[2])
    destination.mkdir(parents=True, exist_ok=True)
    forward, recovery = render(manifest)
    (destination / "cleanup.sql").write_text(forward)
    (destination / "recover.sql").write_text(recovery)
    print(f"Review-only SQL written to {destination}; both scripts roll back.")
