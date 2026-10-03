"""Explicit owned PostgreSQL17 rehearsal; no existing database or credentials."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "source_disposition", ROOT / "tools/prepare_source_disposition.py"
)
disposition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(disposition)
CAPTURE = (
    ROOT
    / "docs/operations/2026-10-03-round21-source-disposition/synthetic-test-capture.json"
)


def capture():
    return json.loads(CAPTURE.read_text())


@pytest.fixture(scope="module")
def pg():
    name = "round21_source_disposition_" + uuid.uuid4().hex
    assert re.fullmatch(r"round21_source_disposition_[a-f0-9]{32}", name)
    endpoint = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
    ).strip()
    assert endpoint.startswith("unix:///"), "Local Docker socket required"
    docker = ["docker", "--host", endpoint]
    subprocess.run(
        docker
        + [
            "run",
            "--rm",
            "--network",
            "none",
            "--name",
            name,
            "-e",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "-d",
            "postgres:17",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    try:
        for attempt in range(80):
            ready = subprocess.run(
                docker
                + ["exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise AssertionError("Owned PostgreSQL startup failed")

        def sql(statement, expected_error=None):
            result = subprocess.run(
                docker
                + [
                    "exec",
                    "-i",
                    name,
                    "psql",
                    "-X",
                    "-qAt",
                    "-h",
                    "/var/run/postgresql",
                    "-U",
                    "postgres",
                    "-d",
                    "postgres",
                    "-v",
                    "ON_ERROR_STOP=1",
                ],
                input=statement,
                text=True,
                capture_output=True,
            )
            if expected_error:
                assert result.returncode != 0, result.stdout
                assert expected_error in result.stderr, result.stderr
            else:
                assert result.returncode == 0, result.stderr
            return result.stdout.strip()

        yield sql
    finally:
        subprocess.run(docker + ["rm", "-f", name], capture_output=True, check=True)


def schema(value):
    columns = []
    for field in sorted(disposition.SOURCE_FIELDS):
        typ = (
            "integer"
            if field in ("id", "country_id", "http_status")
            else "jsonb"
            if field == "metadata"
            else "text"
        )
        columns.append(f'"{field}" {typ}' + (" PRIMARY KEY" if field == "id" else ""))
    statements = [
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        "CREATE TABLE source_documents(" + ",".join(columns) + ");",
    ]
    for fk in value["foreign_keys"]:
        statements.append(
            f'CREATE TABLE "{fk["from_table"]}" (id integer PRIMARY KEY, source_document_id integer, metadata jsonb, CONSTRAINT "{fk["conname"]}" {fk["definition"]});'
        )
    encoded = json.dumps(value["sources"])
    statements.append(
        "INSERT INTO source_documents SELECT * FROM jsonb_populate_recordset(NULL::source_documents,$rows$"
        + encoded
        + "$rows$::jsonb);"
    )
    statements.append(
        "CREATE TABLE entities(id integer PRIMARY KEY, metadata jsonb); INSERT INTO entities VALUES(3,'{\"preserved\":true}');"
    )
    created = disposition.REFERENCE_TABLES | {"source_documents", "entities"}
    existing = {(table, "metadata") for table in created}
    for table, column in existing - disposition.LOGICAL_COLUMNS:
        statements.append(f'ALTER TABLE "{table}" DROP COLUMN "{column}";')
    existing &= disposition.LOGICAL_COLUMNS
    for table, column in sorted(disposition.LOGICAL_COLUMNS):
        if table not in created:
            statements.append(f'CREATE TABLE "{table}"(id integer PRIMARY KEY);')
            created.add(table)
        if (table, column) not in existing:
            statements.append(f'ALTER TABLE "{table}" ADD COLUMN "{column}" jsonb;')
    return "\n".join(statements)


def images(pg):
    return json.loads(
        pg("SELECT jsonb_agg(to_jsonb(s) ORDER BY id) FROM source_documents s;")
    )


def commit_owned_sql(sql):
    assert sql.rstrip().endswith("ROLLBACK;")
    return sql.rstrip()[: -len("ROLLBACK;")] + "COMMIT;"


def test_forward_default_rollback_commit_inverse_and_preservation(pg):
    value = capture()
    pg(schema(value))
    plan, forward, inverse = disposition.render(value)
    original = images(pg)
    pg(forward)
    assert images(pg) == original
    pg(commit_owned_sql(forward))
    assert images(pg) == [c["after"] for c in plan["changes"]]
    pg(inverse)
    assert images(pg) == [c["after"] for c in plan["changes"]]
    pg(commit_owned_sql(inverse))
    assert images(pg) == original
    assert pg("SELECT metadata FROM entities WHERE id=3;") == '{"preserved": true}'


def test_inventory_predicate_runs_on_real_postgresql_jsonb(pg):
    # This executes the actual SQLAlchemy predicate on PostgreSQL, separately
    # from the SQLite-backed endpoint replay.
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy.dialects import postgresql
    from services.source_evidence import publisher_inventory_criterion

    value = capture()
    pg(schema(value))
    criterion = str(
        publisher_inventory_criterion().compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert pg("SELECT count(*) FROM source_documents WHERE " + criterion) == "0"
    pg(
        "INSERT INTO source_documents(id,publisher,status,metadata) VALUES(7000,'National Treasury','ARCHIVED','{\"data_quality\":\"estimated\"}'),(7001,'Government','AVAILABLE','[]'),(7002,'Government','AVAILABLE','true'),(7003,'Government','AVAILABLE','null');"
    )
    assert (
        pg(
            "SELECT string_agg(id::text,',' ORDER BY id) FROM source_documents WHERE "
            + criterion
        )
        == "7000,7001,7002,7003"
    )


@pytest.mark.parametrize(
    "recovery,drift,expected",
    [
        (
            False,
            "UPDATE source_documents SET title='new evidence' WHERE id=1718",
            "Complete source before-image drift",
        ),
        (
            True,
            "UPDATE source_documents SET title='new evidence' WHERE id=1718",
            "Complete source before-image drift",
        ),
        (
            False,
            "INSERT INTO loans VALUES(7000,1707,'{}')",
            "Source dependency present",
        ),
        (True, "INSERT INTO loans VALUES(7000,1718,'{}')", "Source dependency present"),
        (
            False,
            "CREATE TABLE new_source_ref(id int, source_document_id int REFERENCES source_documents(id))",
            "Source FK catalogue drift",
        ),
        (
            True,
            "ALTER TABLE audits DROP CONSTRAINT audits_source_document_id_fkey",
            "Source FK catalogue drift",
        ),
        (
            False,
            'UPDATE entities SET metadata=\'{"nested":{"source_document_ids":[1718]}}\'',
            "Logical source reference present",
        ),
        (
            True,
            'UPDATE entities SET metadata=\'{"nested":{"source_document_id":"1707"}}\'',
            "Logical source reference present",
        ),
        (
            False,
            'UPDATE entities SET metadata=\'{"url":"https://fixtures.example/budgets"}\'',
            "Logical source reference present",
        ),
        (
            True,
            'UPDATE entities SET metadata=\'{"link":"https://www.crakenya.org/county-allocations/"}\'',
            "Logical source reference present",
        ),
        (
            False,
            "UPDATE entities SET metadata='{\"source_document_id\":1707.0}'",
            "Logical source reference present",
        ),
        (
            True,
            'UPDATE entities SET metadata=\'{"source_document_id":" +01718.0 "}\'',
            "Logical source reference present",
        ),
        (
            False,
            'UPDATE entities SET metadata=\'{"link":"https://fixtures.example/budgets#page=1"}\'',
            "Logical source reference present",
        ),
        (
            True,
            "CREATE SCHEMA extra; CREATE TABLE extra.ref(id int, source_document_id int REFERENCES public.source_documents(id))",
            "Source FK outside reviewed public scope",
        ),
        (
            False,
            "ALTER TABLE entities ADD COLUMN new_evidence jsonb",
            "Logical column catalogue drift",
        ),
        (
            True,
            "ALTER TABLE entities DROP COLUMN alt_names",
            "Logical column catalogue drift",
        ),
    ],
)
def test_forward_and_inverse_refuse_drift_atomically(pg, recovery, drift, expected):
    value = capture()
    pg(schema(value))
    _, forward, inverse = disposition.render(value)
    if recovery:
        pg(commit_owned_sql(forward))
    pg(drift + ";")
    before = images(pg)
    pg(inverse if recovery else forward, expected_error=expected)
    assert images(pg) == before
