"""Shared schemas are created only for database consumers and isolated per case."""
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from models import Base, Country


def _shared_engine(request):
    # Inspect the already-loaded parent plugin, avoiding a duplicate conftest import.
    parent = Path(__file__).resolve().parents[1] / "conftest.py"
    plugin = next(plugin for plugin in request.config.pluginmanager.get_plugins()
                  if getattr(plugin, "__file__", None) == str(parent))
    return plugin.engine


def test_case_without_shared_database_does_not_build_a_second_schema(request):
    assert inspect(_shared_engine(request)).get_table_names() == []


@pytest.mark.parametrize("case", ["first", "second"])
def test_committed_rows_and_schema_changes_do_not_leak_to_next_case(db_session, case):
    assert set(inspect(db_session.connection()).get_table_names()) == set(Base.metadata.tables)
    assert db_session.query(Country).count() == 0
    columns = inspect(db_session.connection()).get_columns("countries")
    assert "fixture_extra" not in {column["name"] for column in columns}
    db_session.add(Country(
        id=1, iso_code="KEN", name=case, currency="KES",
        timezone="Africa/Nairobi", default_locale="en_KE",
    ))
    db_session.commit()
    db_session.execute(text("ALTER TABLE countries ADD COLUMN fixture_extra TEXT"))
    db_session.commit()
    assert db_session.query(Country).one().name == case
    assert "fixture_extra" in {
        column["name"] for column in inspect(db_session.connection()).get_columns("countries")
    }


def test_database_teardown_leaves_no_schema_for_nonconsumers(request):
    assert inspect(_shared_engine(request)).get_table_names() == []
