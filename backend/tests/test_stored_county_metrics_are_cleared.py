"""The modelled figures leave the database, not just the response.

``enhanced_county_data.json`` wrote fifteen fields into every county's
``entity.meta["metrics"]`` and a copy of seven of them into
``entity.meta["financial_metrics"]``. Production still holds them. Baringo:

    budget_2025            3,000,433,500   = population x KSh 4,500
    revenue_2024           2,550,368,475   = 85% of that
    debt_outstanding         450,065,025   = 15% of that
    pending_bills            240,034,680   = 8% of that
    missing_funds             60,008,670   = 2% of that
    budget_execution_rate           75.0   the same for 40 counties
    financial_health_score          75.0   the same for 40 counties
    per_capita_budget             4500.0   the input constant, echoed back
    population                   666,763   census 2019 (Mandera's is wrong)
    audit_rating                     "B"   a grade no auditor issued

Every one of those now has a derived source or is withheld, and none of them
reaches a response any more. But "stored but not served" is one endpoint away
from served, and the census that watches this fixture reads the DATABASE — so
it went on reporting the file live, correctly, for figures no reader could
see. Deleting them is what makes the census's answer and the reader's page say
the same thing.

``county_code`` stays: it is an identifier, not a claim about money, and
``/search`` and the entity listing read it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from models import (
    Base,
    Country,
    Entity,
    EntityType,
    FiscalPeriod,
)


# --------------------------------------------------------------------------
# what production looks like, one county
# --------------------------------------------------------------------------

PRODUCTION_META = {
    "metrics": {
        "FY2024/25": {
            "population": 666763,
            "budget_2025": 3000433500,
            "county_code": "030",
            "source_note": "placeholder-seed",
            "audit_rating": "B",
            "revenue_2024": 2550368475,
            "local_revenue": 2550368475,
            "missing_funds": 60008670,
            "pending_bills": 240034680,
            "debt_outstanding": 450065025,
            "per_capita_budget": 4500.0,
            "pending_bills_ratio": 8.0,
            "debt_to_budget_ratio": 15.0,
            "budget_execution_rate": 75.0,
            "financial_health_score": 75.0,
        }
    },
    "financial_metrics": {
        "revenue_2024": 2550368475,
        "local_revenue": 2550368475,
        "missing_funds": 60008670,
        "pending_bills": 240034680,
        "debt_outstanding": 450065025,
        "budget_execution_rate": 75.0,
        "financial_health_score": 75.0,
    },
    "governor": "Benjamin Chesire Cheboi",
    "governor_provenance": {
        "source": "Council of Governors",
        "source_url": "https://cog.go.ke/current-governors/",
    },
    "stalled_projects_count": 3,
    "category": "unknown",
}


@pytest.fixture()
def baringo(db_session):
    """A county holding exactly what production holds today."""
    country = Country(
        name="Kenya",
        iso_code="KEN",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en-KE",
    )
    db_session.add(country)
    db_session.flush()

    entity = Entity(
        country_id=country.id,
        type=EntityType.COUNTY,
        canonical_name="Baringo County",
        slug="baringo-030",
        meta=dict(PRODUCTION_META),
    )
    period = FiscalPeriod(
        country_id=country.id,
        label="FY2024/25",
        start_date=date(2024, 7, 1),
        end_date=date(2025, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    return db_session, entity


def _stored(entity):
    """Every metric key stored on the entity, across fiscal years."""
    out = {}
    for by_year in ((entity.meta or {}).get("metrics") or {}).values():
        if isinstance(by_year, dict):
            out.update(by_year)
    return out


# --------------------------------------------------------------------------
# the purge
# --------------------------------------------------------------------------


class TestThePurge:
    def test_it_removes_the_modelled_metrics(self, baringo):
        import bootstrap

        session, entity = baringo
        bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        left = set(_stored(entity))
        assert left & bootstrap._PURGED_METRIC_FIELDS == set(), (
            f"still stored after the purge: "
            f"{sorted(left & bootstrap._PURGED_METRIC_FIELDS)}"
        )

    def test_it_removes_the_second_copy(self, baringo):
        """``financial_metrics`` holds the same seven figures again.

        Clearing one and leaving the other would take the census green while
        the identical numbers sat under a second key.
        """
        import bootstrap

        session, entity = baringo
        bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        assert "financial_metrics" not in (entity.meta or {})

    def test_it_keeps_the_county_code(self, baringo):
        """An identifier, not a modelled figure — and /search reads it."""
        import bootstrap

        session, entity = baringo
        bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        assert _stored(entity).get("county_code") == "030"

    def test_it_keeps_what_it_did_not_come_for(self, baringo):
        """A purge that took the governor with it would be a different bug."""
        import bootstrap

        session, entity = baringo
        bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        meta = entity.meta or {}
        assert meta.get("governor") == "Benjamin Chesire Cheboi"
        assert meta.get("governor_provenance", {}).get("source") == (
            "Council of Governors"
        )
        assert meta.get("stalled_projects_count") == 3

    def test_it_is_idempotent(self, baringo):
        import bootstrap

        session, entity = baringo
        first = bootstrap.purge_modelled_county_metrics(session)
        session.flush()
        second = bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        assert first["entities_changed"] == 1
        assert second["entities_changed"] == 0
        assert _stored(entity).get("county_code") == "030"

    def test_every_field_the_census_matches_on_is_purged(self):
        """The census would otherwise go green on a partial clean-up.

        It calls the file superseded when no stored figure matches it. If a
        field it matches on survived the purge, the purge would be gaming its
        own gate.
        """
        import bootstrap

        assert set(bootstrap._MODELLED_COUNTY_METRICS) <= (
            bootstrap._PURGED_METRIC_FIELDS
        )


# --------------------------------------------------------------------------
# the census
# --------------------------------------------------------------------------


def _reference_file(provenance):
    import bootstrap

    return next(
        f
        for f in provenance["files"]
        if f["file"] == bootstrap.COUNTY_DATA_PATH.name
    )


class TestTheCensusGoesGreen:
    def test_the_stored_figures_hold_it_stale_first(self, baringo):
        """The starting state, so the test below cannot pass vacuously."""
        import bootstrap

        session, entity = baringo
        fixture = __import__("json").loads(
            bootstrap.COUNTY_DATA_PATH.read_text()
        )["county_data"]["Baringo"]
        meta = dict(entity.meta)
        meta["metrics"] = {
            "FY2024/25": {
                f: fixture[f]
                for f in bootstrap._MODELLED_COUNTY_METRICS
                if fixture.get(f) is not None
            }
        }
        entity.meta = meta
        session.flush()

        f = _reference_file(bootstrap.bootstrap_provenance(session))
        assert f["superseded"] is False
        assert "modelled figures exactly" in f["supersession_evidence"]

    def test_the_purge_takes_it_to_superseded(self, baringo):
        import bootstrap

        session, entity = baringo
        fixture = __import__("json").loads(
            bootstrap.COUNTY_DATA_PATH.read_text()
        )["county_data"]["Baringo"]
        meta = dict(entity.meta)
        meta["metrics"] = {
            "FY2024/25": {
                f: fixture[f]
                for f in bootstrap._MODELLED_COUNTY_METRICS
                if fixture.get(f) is not None
            }
        }
        entity.meta = meta
        session.flush()

        bootstrap.purge_modelled_county_metrics(session)
        session.flush()

        p = bootstrap.bootstrap_provenance(session)
        f = _reference_file(p)
        assert f["superseded"] is True, f["supersession_evidence"]
        assert bootstrap.COUNTY_DATA_PATH.name not in p["stale_files"]


# --------------------------------------------------------------------------
# the seed itself
# --------------------------------------------------------------------------


@pytest.fixture()
def seeded_from_scratch(monkeypatch):
    """A full ``initialize_reference_data`` run against an empty database."""
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker

    import bootstrap

    @compiles(JSONB, "sqlite")
    def _c(t, c, **kw):  # pragma: no cover
        return "TEXT"

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sess = sessionmaker(bind=engine)
    monkeypatch.setattr(bootstrap, "SessionLocal", Sess)

    bootstrap.initialize_reference_data()

    with Sess() as s:
        yield s.query(Entity).filter(Entity.type == EntityType.COUNTY).all()


class TestTheSeedStoresNoneOfIt:
    def test_no_county_is_left_holding_a_modelled_figure(self, seeded_from_scratch):
        """RED before the fix: all 47, on every field.

        The purge alone would not hold — a fresh database re-seeds from the
        same file, so the writer has to stop too.
        """
        import bootstrap

        counties = seeded_from_scratch
        assert len(counties) == 47, f"seed produced {len(counties)} counties"

        offenders = {
            e.canonical_name: sorted(
                set(_stored(e)) & bootstrap._PURGED_METRIC_FIELDS
            )
            for e in counties
            if set(_stored(e)) & bootstrap._PURGED_METRIC_FIELDS
        }
        sample = dict(sorted(offenders.items())[:2])
        assert not offenders, (
            f"{len(offenders)} of {len(counties)} counties still seeded with "
            f"modelled figures, e.g. {sample}"
        )

    def test_no_county_is_left_holding_the_second_copy(self, seeded_from_scratch):
        offenders = [
            e.canonical_name
            for e in seeded_from_scratch
            if "financial_metrics" in (e.meta or {})
        ]
        assert not offenders, (
            f"{len(offenders)} counties still hold financial_metrics, e.g. "
            f"{sorted(offenders)[:2]}"
        )

    def test_the_county_code_is_still_seeded(self, seeded_from_scratch):
        """Removing the modelled figures must not take the identifier."""
        coded = [e for e in seeded_from_scratch if _stored(e).get("county_code")]
        assert len(coded) == 47, f"only {len(coded)} counties kept a county_code"


# --------------------------------------------------------------------------
# the one reader that was standing on the stored copy
# --------------------------------------------------------------------------


class TestAbsentPopulationIsNotZero:
    """``metrics["population"]`` was the county page's second rung.

    All 47 counties have a census row today, so the rung is unreachable in
    production — but it was reached by defaulting to 0, which states that a
    county has no residents. Removing the stored copy without fixing that
    would have turned a wrong number into a wronger one.
    """

    @pytest.fixture()
    def county_without_a_census_row(self, db_session, seed_country):
        entity = Entity(
            id=901,
            country_id=seed_country.id,
            type=EntityType.COUNTY,
            canonical_name="Isiolo County",
            slug="isiolo-901",
            meta={"metrics": {"FY2024/25": {"county_code": "011"}}},
        )
        db_session.add(entity)
        db_session.commit()
        return entity

    def test_population_is_absent_not_zero(self, client, county_without_a_census_row):
        resp = client.get(
            f"/api/v1/counties/{county_without_a_census_row.id}/comprehensive"
        )
        assert resp.status_code == 200, resp.text
        demographics = resp.json()["demographics"]

        assert demographics["population"] is None, (
            "a county with no census row was published as having 0 residents"
        )
        assert demographics["population_year"] is None

    def test_per_capita_budget_is_absent_too(self, client, county_without_a_census_row):
        """0 residents divided into a budget is not KSh 0 per resident."""
        resp = client.get(
            f"/api/v1/counties/{county_without_a_census_row.id}/comprehensive"
        )
        assert resp.status_code == 200, resp.text

        assert resp.json()["budget"]["per_capita_budget"] is None


# --------------------------------------------------------------------------
# the migration that reaches production
# --------------------------------------------------------------------------


def _load_migration(name):
    import importlib.util
    import pathlib

    path = (
        pathlib.Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"mig_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestTheMigration:
    """The seed fix alone never reaches production.

    ``initialize_reference_data`` skips the county loop once 47 counties
    exist, which they have since 2025 — so production's copies would sit there
    untouched however clean the writer became. This is the only path that
    removes them.
    """

    def test_it_clears_a_production_shaped_row(self, baringo, monkeypatch):
        session, entity = baringo
        migration = _load_migration("ce6ed007f696_clear_the_modelled_county_metrics")
        monkeypatch.setattr(
            migration.op, "get_bind", lambda: session.connection(), raising=False
        )

        migration.upgrade()

        session.expire_all()
        reloaded = session.query(Entity).filter(Entity.id == entity.id).one()
        left = set(_stored(reloaded))
        import bootstrap

        assert left & bootstrap._PURGED_METRIC_FIELDS == set()
        assert "financial_metrics" not in (reloaded.meta or {})
        assert _stored(reloaded).get("county_code") == "030"

    def test_the_chain_still_has_one_head(self):
        """A second head makes ``alembic upgrade head`` fail on deploy."""
        import pathlib
        import re

        versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
        revisions, parents = set(), set()
        for path in versions.glob("*.py"):
            text = path.read_text()
            rev = re.search(r"^revision = ['\"]([^'\"]+)['\"]", text, re.M)
            down = re.search(r"^down_revision = ['\"]([^'\"]+)['\"]", text, re.M)
            if rev:
                revisions.add(rev.group(1))
            if down:
                parents.add(down.group(1))

        heads = revisions - parents
        assert heads == {"ce6ed007f696"}, f"expected one head, found {sorted(heads)}"
