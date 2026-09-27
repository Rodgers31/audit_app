"""Rehearse review-only cleanup against a disposable, local PostgreSQL database.

Requires an already-running local Docker PostgreSQL container (default: pg-test,
published at 127.0.0.1:55432), using its local postgres socket. No credentials,
environment files, production connections, or existing database writes are used.
The database name is generated internally and dropped in finally. Captured JSON
before-images are real; the schema and related FK control rows are synthetic.

Example:
  python tools/verify_sourced_record_cleanup.py
"""

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from prepare_legacy_evidence_cleanup import render


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "docs/operations/2026-09-27-sourced-records"
PREFIX = "sourced_cleanup_rehearsal_"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def literal(value):
    tag = "$rehearsal_payload$"
    payload = json.dumps(value, ensure_ascii=False, allow_nan=False)
    require(tag not in payload, "Unsafe SQL delimiter")
    return f"{tag}{payload}{tag}::jsonb"


def committed(sql):
    """Change only the terminal rollback, only for our disposable DB."""
    require(sql.rstrip().endswith("ROLLBACK;"), "Missing terminal ROLLBACK")
    require(len(re.findall(r"(?m)^ROLLBACK;$", sql)) == 1, "Unexpected rollback count")
    return sql.rstrip()[: -len("ROLLBACK;")] + "COMMIT;\n"


class LocalDatabase:
    def __init__(self, host, port, container):
        require(host in {"localhost", "127.0.0.1", "::1"}, "Localhost is mandatory")
        require(
            isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535,
            "Invalid local port",
        )
        self.name = PREFIX + uuid.uuid4().hex
        require(
            re.fullmatch(PREFIX + r"[a-f0-9]{32}", self.name), "Unsafe database name"
        )
        endpoint = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        require(
            endpoint.startswith("unix:///"),
            "Docker endpoint must be a local Unix socket",
        )
        self.docker = ["docker", "--host", endpoint]
        self.container = container
        inspection = self.command(["inspect", container])
        details = json.loads(inspection.stdout)
        require(
            len(details) == 1 and details[0]["State"]["Running"],
            "Container is not running",
        )
        ports = details[0]["NetworkSettings"]["Ports"].get("5432/tcp") or []
        require(
            any(p["HostPort"] == str(port) for p in ports),
            "Wrong local PostgreSQL port",
        )
        self.created = False

    def command(self, args, **kwargs):
        return subprocess.run(
            self.docker + args, capture_output=True, text=True, **kwargs
        )

    def sql(self, sql, *, admin=False, expect_error=None):
        require(
            re.fullmatch(PREFIX + r"[a-f0-9]{32}", self.name), "Unsafe database name"
        )
        result = self.command(
            [
                "exec",
                "-i",
                self.container,
                "psql",
                "-X",
                "-q",
                "-A",
                "-t",
                "-h",
                "/var/run/postgresql",
                "-p",
                "5432",
                "-U",
                "postgres",
                "-v",
                "ON_ERROR_STOP=1",
                "-d",
                "postgres" if admin else self.name,
            ],
            input=sql,
        )
        if expect_error is not None:
            require(result.returncode != 0, f"Unsafe success; expected: {expect_error}")
            require(expect_error in result.stderr, f"Wrong failure: {result.stderr}")
            return result.stderr.strip()
        require(result.returncode == 0, result.stderr)
        return result.stdout.strip()

    def create(self):
        self.sql(f'CREATE DATABASE "{self.name}";', admin=True)
        self.created = True
        require(self.sql("SELECT current_database();") == self.name, "Wrong database")

    def close(self):
        if self.created:
            self.sql(f'DROP DATABASE "{self.name}";', admin=True)
            self.created = False


def schema_and_rows(manifest, proposal):
    """Use captured JSON rows verbatim; add explicit synthetic FK controls."""
    audit = manifest["delete_audits"][0]
    document = manifest["retired_source_document"]
    require(
        set(audit) == set().union(*(set(a) for a in manifest["delete_audits"])),
        "Audit rows have inconsistent shapes",
    )
    json_fields = {"provenance", "validation_warnings", "metadata"}
    integer_fields = {
        "id",
        "entity_id",
        "period_id",
        "source_document_id",
        "extraction_id",
        "audit_year",
        "country_id",
        "http_status",
    }
    numeric_fields = {"amount", "confidence_score"}

    def columns(row):
        result = []
        for key in row:
            require(re.fullmatch(r"[a-z_][a-z0-9_]*", key), "Unsafe column name")
            kind = (
                "jsonb"
                if key in json_fields
                else "integer"
                if key in integer_fields
                else "numeric"
                if key in numeric_fields
                else "boolean"
                if key == "publishable"
                else "text"
            )
            result.append(f'"{key}" {kind}' + (" PRIMARY KEY" if key == "id" else ""))
        return ",".join(result)

    entities = []
    by_id = {e["id"]: e for e in manifest["entities"]}
    for row in proposal["identities"]:
        entities.append(
            {**row, "type": "COUNTY", "metadata": by_id[row["id"]]["before"]}
        )
    for entity_id in sorted(
        {a["entity_id"] for a in manifest["delete_audits"]} - set(by_id)
    ):
        entities.append(
            {
                "id": entity_id,
                "canonical_name": f"Synthetic parent {entity_id}",
                "slug": f"synthetic-{entity_id}",
                "type": "MINISTRY",
                "metadata": {},
            }
        )
    sql = f"""
DROP SCHEMA public CASCADE;
CREATE SCHEMA public;
CREATE TABLE entities(id int PRIMARY KEY, canonical_name text NOT NULL,
 slug text NOT NULL UNIQUE, type text NOT NULL, metadata jsonb NOT NULL);
CREATE TABLE fiscal_periods(id int PRIMARY KEY);
CREATE TABLE source_documents({columns(document)});
CREATE TABLE audits({columns(audit)},
 FOREIGN KEY(entity_id) REFERENCES entities(id),
 FOREIGN KEY(period_id) REFERENCES fiscal_periods(id),
 FOREIGN KEY(source_document_id) REFERENCES source_documents(id));
CREATE TABLE budget_lines(id int PRIMARY KEY, entity_id int REFERENCES entities(id),
 period_id int REFERENCES fiscal_periods(id),
 source_document_id int REFERENCES source_documents(id), amount numeric NOT NULL);
INSERT INTO entities SELECT * FROM jsonb_populate_recordset(NULL::entities, {literal(entities)});
INSERT INTO fiscal_periods SELECT DISTINCT period_id FROM
 jsonb_populate_recordset(NULL::audits, {literal(manifest['delete_audits'])});
INSERT INTO source_documents SELECT * FROM
 jsonb_populate_record(NULL::source_documents, {literal(document)});
INSERT INTO audits SELECT * FROM
 jsonb_populate_recordset(NULL::audits, {literal(manifest['delete_audits'])});
INSERT INTO budget_lines VALUES (1000003,3,9,1836,123.45),(1000004,4,9,1836,678.90);
"""
    return sql


def snapshot(db):
    value = db.sql(
        """SELECT jsonb_build_object(
      'entities',(SELECT jsonb_agg(to_jsonb(e) ORDER BY id) FROM entities e),
      'audits',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM audits a),'[]'::jsonb),
      'source_documents',(SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM source_documents d),
      'budget_lines',(SELECT jsonb_agg(to_jsonb(b) ORDER BY id) FROM budget_lines b),
      'fiscal_periods',(SELECT jsonb_agg(to_jsonb(f) ORDER BY id) FROM fiscal_periods f),
      'foreign_keys',(SELECT jsonb_agg(pg_get_constraintdef(oid) ORDER BY conname)
        FROM pg_constraint WHERE contype='f' AND connamespace='public'::regnamespace)
    );"""
    )
    return json.loads(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=55432)
    parser.add_argument("--container", default="pg-test")
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    paths = {
        name: args.artifacts / name
        for name in (
            "cleanup-current-manifest.json",
            "cleanup-after-codes-manifest.json",
            "county-code-proposal.json",
            "county-codes.sql",
            "county-code-recovery.sql",
        )
    }
    receipt_path = args.receipt or args.artifacts / "cleanup-rehearsal.json"
    receipt = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "production_writes": False,
        "input_sha256": {},
        "checks": [],
        "scope": "Disposable local PostgreSQL; captured complete cleanup before-images, synthetic schema and related FK controls",
        "limitations": [
            "Not a full production schema/data restore, production execution, or authorization.",
            "Synthetic related budget rows prove preservation for the exercised FKs; no claim about all production tables.",
            "Current and projected manifests remain unapproved and must be recaptured after shared source refreshes.",
            "County-code recovery changes only four paths and intentionally preserves unrelated newer metadata.",
        ],
    }
    db = None
    try:
        for name, path in paths.items():
            receipt["input_sha256"][name] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        for path in (Path(__file__), ROOT / "tools/prepare_legacy_evidence_cleanup.py"):
            receipt["input_sha256"][str(path.relative_to(ROOT))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
        manifest = json.loads(paths["cleanup-current-manifest.json"].read_text())
        projected = json.loads(paths["cleanup-after-codes-manifest.json"].read_text())
        proposal = json.loads(paths["county-code-proposal.json"].read_text())
        review_cleanup, review_recover = render(manifest)
        cleanup, recover = map(committed, (review_cleanup, review_recover))
        after_cleanup, after_recover = map(committed, render(projected))
        codes = committed(paths["county-codes.sql"].read_text())
        codes_recover = committed(paths["county-code-recovery.sql"].read_text())
        setup = schema_and_rows(manifest, proposal)
        db = LocalDatabase(args.host, args.port, args.container)
        db.create()
        receipt["database"] = db.name
        receipt["postgres_version"] = db.sql("SELECT version();")

        def check(name, condition, **details):
            require(condition, name)
            receipt["checks"].append({"name": name, "passed": True, **details})

        def reset():
            db.sql(setup)
            return snapshot(db)

        def refusal(name, script, expected):
            before = snapshot(db)
            error = db.sql(script, expect_error=expected)
            check(
                name,
                snapshot(db) == before,
                expected_error=error,
                transaction_unchanged=True,
            )

        baseline = reset()
        check(
            "captured audit and document before-images loaded exactly",
            baseline["audits"] == manifest["delete_audits"]
            and baseline["source_documents"] == [manifest["retired_source_document"]],
        )
        db.sql(review_cleanup)
        check("default cleanup script rolls back", snapshot(db) == baseline)
        db.sql(cleanup)
        cleaned = snapshot(db)
        expected = copy.deepcopy(baseline)
        expected["audits"] = []
        for row in expected["entities"]:
            match = next(
                (e for e in manifest["entities"] if e["id"] == row["id"]), None
            )
            if match:
                row["metadata"] = match["after"]
        check(
            "current cleanup changes only approved metadata keys and 25 audit rows",
            cleaned == expected,
            county_rows=47,
            retired_audit_rows=25,
            synthetic_budget_rows_unchanged=2,
        )
        db.sql(review_recover)
        check("default recovery script rolls back", snapshot(db) == cleaned)
        db.sql(recover)
        check(
            "current cleanup recovery restores exact complete baseline",
            snapshot(db) == baseline,
        )

        db.sql(paths["county-codes.sql"].read_text())
        check("default county code script rolls back", snapshot(db) == baseline)
        db.sql(codes)
        corrected = snapshot(db)
        expected = copy.deepcopy(baseline)
        for edit in proposal["proposed_edits"]:
            row = next(e for e in expected["entities"] if e["id"] == edit["entity_id"])
            for cell in edit["edits"]:
                a, b, c = cell["path"]
                row["metadata"][a][b][c] = cell["after"]
        check(
            "county code correction changes exactly four cells; IDs and FKs preserved",
            corrected == expected,
        )
        refusal(
            "stale pre-code cleanup manifest refuses corrected cells",
            cleanup,
            "Entity snapshot drift",
        )
        db.sql(after_cleanup)
        check(
            "projected cleanup keeps corrected cells and FK controls",
            snapshot(db)["budget_lines"] == baseline["budget_lines"]
            and snapshot(db)["foreign_keys"] == baseline["foreign_keys"]
            and not snapshot(db)["audits"],
        )
        db.sql(after_recover)
        check(
            "projected cleanup recovery restores exact post-code state",
            snapshot(db) == corrected,
        )
        db.sql(paths["county-code-recovery.sql"].read_text())
        check("default county code recovery rolls back", snapshot(db) == corrected)
        db.sql(codes_recover)
        check("county code recovery restores exact baseline", snapshot(db) == baseline)

        for name, mutation, expected_error in (
            (
                "metadata drift",
                "UPDATE entities SET metadata=metadata || '{\"new_source\":true}'::jsonb WHERE id=3;",
                "Entity snapshot drift",
            ),
            (
                "source-document drift",
                "UPDATE source_documents SET url='https://example.invalid/new-source' WHERE id=1836;",
                "Retired source document drift",
            ),
            (
                "audit row drift",
                "UPDATE audits SET finding_text='new sourced finding' WHERE id=870;",
                "Audit snapshot drift",
            ),
            (
                "new inbound audit FK",
                "CREATE TABLE new_audit_reference(id int PRIMARY KEY, audit_id int REFERENCES audits(id)); INSERT INTO new_audit_reference VALUES (1,870);",
                "Audit references changed",
            ),
        ):
            reset()
            db.sql(mutation)
            refusal("cleanup refuses " + name, cleanup, expected_error)

        reset()
        db.sql(
            "UPDATE entities SET metadata=jsonb_set(metadata,'{metrics,FY2024/25,county_code}','\"999\"') WHERE id=3;"
        )
        refusal(
            "county code forward refuses changed code cell",
            codes,
            "Expected four metadata cells changed",
        )
        reset()
        db.sql("UPDATE entities SET slug='new-county-identity' WHERE id=49;")
        refusal(
            "county code forward guards all 47 identities",
            codes,
            "County identity snapshot changed",
        )

        for name, mutation, expected_error in (
            (
                "newer metadata",
                "UPDATE entities SET metadata=metadata || '{\"new_source\":true}'::jsonb WHERE id=3;",
                "Post-cleanup entity drift",
            ),
            (
                "newer source document",
                "UPDATE source_documents SET url='https://example.invalid/new-source' WHERE id=1836;",
                "Retired source document drift",
            ),
            (
                "new inbound audit FK",
                "CREATE TABLE new_audit_reference(id int PRIMARY KEY, audit_id int REFERENCES audits(id));",
                "Audit references changed",
            ),
            (
                "occupied audit ID",
                f"INSERT INTO audits SELECT * FROM jsonb_populate_record(NULL::audits, {literal(manifest['delete_audits'][0])});",
                "Audit IDs occupied",
            ),
        ):
            reset()
            db.sql(cleanup)
            db.sql(mutation)
            refusal("cleanup recovery refuses " + name, recover, expected_error)

        for name, mutation, expected_error in (
            (
                "newer code cell",
                "UPDATE entities SET metadata=jsonb_set(metadata,'{metrics,FY2024/25,county_code}','\"999\"') WHERE id=3;",
                "Post-correction code cells changed",
            ),
            (
                "changed county identity",
                "UPDATE entities SET slug='new-county-identity' WHERE id=49;",
                "County identity snapshot changed",
            ),
        ):
            reset()
            db.sql(codes)
            db.sql(mutation)
            refusal(
                "county code recovery refuses " + name, codes_recover, expected_error
            )

        baseline = reset()
        db.sql(codes)
        db.sql(
            "UPDATE entities SET metadata=metadata || '{\"new_source\":true}'::jsonb WHERE id=3;"
        )
        db.sql(codes_recover)
        next(e for e in baseline["entities"] if e["id"] == 3)["metadata"][
            "new_source"
        ] = True
        check(
            "county code recovery preserves unrelated newer metadata",
            snapshot(db) == baseline,
        )
        receipt["passed"] = True
    except Exception as exc:
        receipt["failure"] = str(exc)
        raise
    finally:
        if db is not None:
            try:
                db.close()
                receipt["disposable_database_removed"] = not db.created
            except Exception as exc:
                receipt["passed"] = False
                receipt["database_cleanup_error"] = str(exc)
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        print(
            json.dumps(
                {
                    "passed": receipt["passed"],
                    "checks": len(receipt["checks"]),
                    "receipt": str(receipt_path),
                }
            )
        )
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
