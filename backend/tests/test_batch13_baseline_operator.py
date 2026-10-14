"""Real owned PostgreSQL maintenance boundary; never a provider equivalence proof."""
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from test_batch9_reconciliation import owned, native, read  # noqa: F401
from seeding.reconciliation import ReconciliationRefused, _maintenance


def test_non_superuser_still_refuses_under_closed_admission(owned):
    selected = native(owned)
    before = read(owned, "SELECT * FROM seeding_domain_claims")
    role = "batch13_inert_" + uuid4().hex
    # Role is NOLOGIN and exists only in our owned cluster. It models the
    # observed privilege limitation without claiming provider configuration.
    with owned.admin.connect() as admin:
        admin.execute(text(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS'))
    owned.admission(False)
    try:
        connection = owned.connection
        pid = connection.scalar(text("SELECT pg_backend_pid()"))
        connection.execute(text(f'SET ROLE "{role}"'))
        assert connection.scalar(text("SELECT rolsuper FROM pg_roles WHERE rolname=current_user")) is False
        with pytest.raises(ReconciliationRefused, match="Complete database visibility and maintenance privilege required"):
            _maintenance(connection)
        connection.execute(text("RESET ROLE"))
        connection.commit()
        assert connection.scalar(text("SELECT pg_backend_pid()")) == pid
        _maintenance(connection)
        assert read(owned, "SELECT * FROM seeding_domain_claims") == before
        assert str(before[0]["id"]) == selected["claim_id"]
    finally:
        owned.connection.rollback()
        owned.connection.execute(text("RESET ROLE"))
        owned.connection.commit()
        with owned.admin.connect() as admin:
            admin.execute(text(f'DROP ROLE "{role}"'))


def test_admission_close_preserves_exact_session_and_refuses_new_client(owned):
    connection = owned.connection
    pid = connection.scalar(text("SELECT pg_backend_pid()"))
    connection.commit()
    owned.admission(False)
    with pytest.raises(DBAPIError):
        with owned.engine.connect():
            pytest.fail("Closed owned database admitted a new client")
    assert connection.scalar(text("SELECT pg_backend_pid()")) == pid
    assert connection.scalar(text("SELECT datallowconn FROM pg_database WHERE datname=current_database()")) is False
    _maintenance(connection)
