"""The deployed schema must have every column the models select.

REGRESSION FIXTURE for the defect found 2026-08-30: production's
``public.users`` had 6 of the 9 columns ``models.User`` declares, so
``db.query(User)`` — which selects every mapped column — raised
``column users.display_name does not exist`` on every Supabase-authenticated
request. Migration ``d1a7c9e40b12`` adds them.

The exact drift is pinned in :class:`TestTheProductionDefect` below: that case
fails against the pre-fix schema and passes against the post-fix one.

Note what is NOT tested here, on purpose. A parity assertion against this
suite's own database is vacuous — ``conftest`` builds it with
``Base.metadata.create_all()``, so it matches the models by construction and
could never have caught this. The comparison LOGIC is unit-tested here; the
comparison itself has to run against the real deployed database, which is what
the ``migrate`` job does after ``alembic upgrade head``.
"""

from __future__ import annotations

import pytest
from services.schema_parity import (
    check_database,
    find_missing_columns,
    format_report,
)

# public.users as production actually had it on 2026-08-30, and as
# models.User declares it.
PROD_USERS = ["created_at", "disabled", "email", "id", "password_hash", "roles"]
MODEL_USERS = PROD_USERS + ["display_name", "email_verified", "updated_at"]


class TestTheProductionDefect:
    def test_the_exact_drift_is_reported(self):
        missing = find_missing_columns({"users": PROD_USERS}, {"users": MODEL_USERS})
        assert missing == {
            "users": ["display_name", "email_verified", "updated_at"]
        }

    def test_after_the_migration_there_is_no_drift(self):
        """Post-``d1a7c9e40b12`` state — the same check must go quiet."""
        assert find_missing_columns({"users": MODEL_USERS}, {"users": MODEL_USERS}) == {}

    def test_the_report_names_the_columns_and_the_consequence(self):
        report = format_report(
            find_missing_columns({"users": PROD_USERS}, {"users": MODEL_USERS})
        )
        assert "users: display_name, email_verified, updated_at" in report
        assert "UndefinedColumn" in report


class TestComparisonRules:
    def test_extra_database_columns_are_not_drift(self):
        """Supabase adds its own columns and hand-tuned tables carry more than
        the models map. Flagging those would produce noise nobody acts on."""
        live = {"users": MODEL_USERS + ["banned_until", "is_sso_user"]}
        assert find_missing_columns(live, {"users": MODEL_USERS}) == {}

    def test_a_missing_table_reports_all_its_columns(self):
        """Same failure, bigger blast radius — it must not be silently
        skipped just because the table is absent rather than thin."""
        assert find_missing_columns({}, {"extractions": ["id", "page_no"]}) == {
            "extractions": ["id", "page_no"]
        }

    def test_ignored_tables_are_skipped(self):
        assert (
            find_missing_columns(
                {}, {"users": MODEL_USERS}, ignore_tables=["users"]
            )
            == {}
        )

    def test_a_matching_schema_is_reported_as_ok(self):
        assert "OK" in format_report({})


class TestAgainstALiveEngine:
    def test_reads_columns_from_a_real_database(self, db_session):
        """The engine path must actually inspect, not just pass a dict
        through. Runs against the suite's own SQLite database, which is built
        from the models — so the ONLY defensible assertion here is that the
        inspection returns something, not that parity holds."""
        from models import Base

        engine = db_session.get_bind()
        missing = check_database(engine, Base.metadata)
        assert isinstance(missing, dict)

    def test_a_model_the_database_lacks_is_caught_on_a_live_engine(self):
        """POSITIVE CONTROL for the engine path: give it metadata describing a
        table that does not exist, and it must report it. Without this, the
        test above passes on an engine that inspected nothing."""
        from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

        engine = create_engine("sqlite://")
        md = MetaData()
        Table("never_created", md, Column("id", Integer), Column("x", String))
        assert check_database(engine, md) == {"never_created": ["id", "x"]}
