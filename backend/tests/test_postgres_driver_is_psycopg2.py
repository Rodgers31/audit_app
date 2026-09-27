"""Every Postgres engine this repo builds must load psycopg2 (issue #228).

On 2026-09-25 an unpinned ``pip install`` pulled SQLAlchemy 2.1.0, which
resolves a bare ``postgresql://`` URL to psycopg (v3). requirements.txt ships
psycopg2-binary only, so ``alembic upgrade`` (alembic/env.py) and
``import database`` both died with ``No module named 'psycopg'``: the nightly
seed was skipped, the backend suite could not load conftest.py, and the next
Render deploy would have crash-looped at boot.

The behavioural tests run the real entry points in a fresh interpreter, the way
the workflow steps do, so they need neither conftest.py nor a live database:
an engine that reached psycopg2 fails with ``psycopg2.OperationalError`` on a
closed port, one that did not fails on the import first.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest
from packaging.requirements import Requirement

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent

# Port 1 is closed, so a connection attempt fails fast without a server.
_CLOSED = "u:p%40ss@127.0.0.1:1/db?sslmode=disable&connect_timeout=3"

URL_FORMS = [
    f"postgresql://{_CLOSED}",
    f"postgres://{_CLOSED}",
    f"postgresql+psycopg2://{_CLOSED}",
]


def _run(args: list[str], database_url: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("DB_")}
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, *args],
        cwd=_BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("url", URL_FORMS)
def test_app_engine_loads_psycopg2(url):
    """``import database`` is what the seed and validate steps do first."""
    probe = (
        "import json, database as d;"
        "u = d.engine.url;"
        "print(json.dumps({'driver': d.engine.dialect.driver,"
        " 'dbapi': d.engine.dialect.dbapi.__name__,"
        " 'password': u.password, 'query': dict(u.query)}))"
    )
    proc = _run(["-c", probe], url)
    assert proc.returncode == 0, proc.stderr[-2000:]
    got = json.loads(proc.stdout.strip().splitlines()[-1])
    assert got["driver"] == "psycopg2"
    assert got["dbapi"] == "psycopg2"
    # Only the scheme may change: credentials and query must survive intact.
    assert got["password"] == "p@ss"
    assert got["query"] == {"sslmode": "disable", "connect_timeout": "3"}


@pytest.mark.parametrize("url", URL_FORMS)
def test_alembic_online_reaches_psycopg2(url):
    """The "Run alembic migrations" step failed at env.py engine_from_config."""
    proc = _run(["-m", "alembic", "current"], url)
    assert proc.returncode != 0, "a closed port cannot have served a migration"
    assert "No module named" not in proc.stderr, proc.stderr[-2000:]
    assert "(psycopg2.OperationalError)" in proc.stderr, proc.stderr[-2000:]


# ── the helper itself ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url, expected",
    [
        ("postgresql://u:p@h:6543/db", "postgresql+psycopg2://u:p@h:6543/db"),
        ("postgres://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("POSTGRESQL://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        # Query strings and percent-encoding come back byte-for-byte.
        (
            "postgresql://u:p%40s%25s@h/db?sslmode=require&options=-c%20search_path%3Dx",
            "postgresql+psycopg2://u:p%40s%25s@h/db?sslmode=require&options=-c%20search_path%3Dx",
        ),
        # A named driver or another database is left alone.
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql+asyncpg://u:p@h/db", "postgresql+asyncpg://u:p@h/db"),
        ("sqlite://", "sqlite://"),
        ("sqlite:///./test.db", "sqlite:///./test.db"),
        ("not a url", "not a url"),
    ],
)
def test_with_explicit_driver(url, expected):
    from db_url import with_explicit_driver

    assert with_explicit_driver(url) == expected


# ── what the installers are allowed to pull ────────────────────────────


def _sqlalchemy_requirement() -> Requirement:
    lines = [
        line.strip()
        for line in (_BACKEND / "requirements.txt").read_text().splitlines()
        if re.match(r"(?i)sqlalchemy\b", line.strip())
    ]
    # ci.yml and docker-build-deploy.yml grep this one line out of the file.
    assert len(lines) == 1, lines
    return Requirement(lines[0])


def test_requirements_exclude_sqlalchemy_2_1():
    spec = _sqlalchemy_requirement().specifier
    assert "2.0.54" in spec, "the last version the nightly passed on"
    assert "2.1.0" not in spec, "2.1.0 broke every engine (issue #228)"
    assert "2.1.1" not in spec


def test_no_workflow_installs_bare_sqlalchemy():
    """ci.yml and docker-build-deploy.yml ran ``pip install alembic sqlalchemy``,
    which ignores requirements.txt, so the pin alone would not have reached them."""
    bare = re.compile(r"(?i)^sqlalchemy(\[[^\]]*\])?$")
    offenders = []
    for wf in sorted((_REPO / ".github" / "workflows").glob("*.y*ml")):
        for n, line in enumerate(wf.read_text().splitlines(), 1):
            if "pip install" not in line:
                continue
            if any(bare.match(tok.strip("'\"")) for tok in line.split()):
                offenders.append(f"{wf.name}:{n}: {line.strip()}")
    assert not offenders, offenders
