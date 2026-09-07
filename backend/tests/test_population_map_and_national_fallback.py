"""A population map that always returned {}, and a fallback that never returned Kenya.

Measured against production on 2026-09-07 (alembic ``f4a1c07b9e52``).
``population_data`` holds 66 rows: 47 county rows at 2019, two rows attributed
to the National Government entity (id 73), and 17 ``entity_id IS NULL`` rows
carrying the World Bank series 2010-2025.

    id | entity_id | entity              | type     | year | total_population | doc
    64 | 73        | National Government | NATIONAL | 2019 |       47,564,296 | 1823
    69 | 73        | National Government | NATIONAL | 2026 |               82 | NULL
    85 | NULL      | -                   | -        | 2025 |       57,532,493 | NULL

id=69 is what these three faults have in common. It was written 2026-03-01
06:00:16 with confidence 1.00, no ``source_document_id``, no ``extraction_id``
and ``metadata`` ``{}``.

WHAT REACHES A READER, AND WHAT DOES NOT
----------------------------------------
id=69 is **shadowed, not published**. ``services/population.py:40`` prefers the
``entity_id IS NULL`` series, so ``/api/v1/economic/population/latest`` returns
57,532,493 for 2025 and is correct. Saying that plainly matters more than the
headline number: what follows is about two paths that would reach a reader, not
one that does.

``_get_population_map``'s caller, ``/api/v1/pending-bills/summary``, does not
reach the map today either: ``pending_bills`` holds 0 rows on production, so
the endpoint takes its ``if not bills`` branch into
``_pending_bills_summary_from_loans`` (59 ``loans`` rows carry
``debt_category = PENDING_BILLS``). The defect is latent, and becomes live the
first time the pending_bills domain seeds.

THE THREE FAULTS
----------------
1. ``PopulationData`` has no ``population`` attribute — the column is
   ``total_population``. ``hasattr(PopulationData, "population")`` is False, and
   ``_get_population_map``'s ``except Exception: return {}`` swallowed the
   AttributeError, so the function returned ``{}`` on every call ever made.

2. It took a single global ``MAX(year)`` across all entity-bearing rows. That
   is 2026 — id=69 — which selects the National Government and excludes all 47
   counties. The docstring says "latest PopulationData" and means latest PER
   ENTITY.

   The two faults are independent, and fixing only the first would have been
   worse than fixing neither: the map would then have contained
   ``{"National Government": 82}``, and a pending bill filed against the
   national entity would have published ``amount / 82`` as a per-capita figure.

3. ``latest_national_population``'s fallback sums ``total_population`` over
   ``entity_id IS NOT NULL`` at ``MAX(year)``. On production that filter admits
   the National Government entity rows, not only counties, so it has never had
   a year in which it returns Kenya's population:

       at 2026 (max year today)  ->  82
       at 2019 (if id=69 were gone)  ->  95,128,592, which is exactly
                                         47,564,296 x 2: the 47 counties plus
                                         id=64 double-counted

   A "does this year cover enough counties?" guard does not catch the second
   case — 2019 covers all 47 counties and the sum is still double.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from models import Base, Country, Entity, EntityType, PopulationData
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from main import _get_population_map
from services.population import latest_national_population


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


# Production figures, so a failure message names something checkable.
NATIONAL_2019 = 47_564_296  # id=64, source_document 1823
WORLD_BANK_2025 = 57_532_493  # id=85, the series /population/latest serves
ID_69 = 82  # National Government, 2026, no source document
NAIROBI_2019 = 4_397_073
BARINGO_2019 = 666_763


@pytest.fixture()
def db(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'pop.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _country(session: Session) -> Country:
    country = session.query(Country).filter(Country.iso_code == "KE").first()
    if country is None:
        country = Country(
            name="Kenya",
            iso_code="KE",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en-KE",
        )
        session.add(country)
        session.flush()
    return country


def _entity(session: Session, name: str, kind: EntityType) -> Entity:
    entity = Entity(
        country_id=_country(session).id,
        canonical_name=name,
        slug=name.lower().replace(" ", "-"),
        type=kind,
    )
    session.add(entity)
    session.flush()
    return entity


def _production_shape(session: Session) -> dict:
    """The rows production actually holds, minus the World Bank series.

    The World Bank rows are added by the tests that need them, so a test can
    say what happens when that series is present and when it is gone.
    """
    national = _entity(session, "National Government", EntityType.NATIONAL)
    nairobi = _entity(session, "Nairobi", EntityType.COUNTY)
    baringo = _entity(session, "Baringo", EntityType.COUNTY)

    session.add_all(
        [
            # id=64 — the census figure, with a source document.
            PopulationData(
                entity_id=national.id,
                year=2019,
                total_population=NATIONAL_2019,
                source_document_id=1823,
            ),
            # id=69 — 82 people, no source document, year = the year it was written.
            PopulationData(entity_id=national.id, year=2026, total_population=ID_69),
            PopulationData(
                entity_id=nairobi.id, year=2019, total_population=NAIROBI_2019
            ),
            PopulationData(
                entity_id=baringo.id, year=2019, total_population=BARINGO_2019
            ),
        ]
    )
    session.commit()
    return {"national": national, "nairobi": nairobi, "baringo": baringo}


class TestPopulationMap:
    """``_get_population_map`` must return the counties it promises."""

    def test_it_returns_county_populations_instead_of_an_empty_map(self, db):
        """The headline defect: ``{}`` on every call since it was written.

        Two independent causes, and this asserts the outcome rather than
        either mechanism: ``p.population`` does not exist, and the global
        ``MAX(year)`` of 2026 selects only id=69's entity.
        """
        _production_shape(db)

        assert _get_population_map(db) == {
            "Nairobi": NAIROBI_2019,
            "Baringo": BARINGO_2019,
        }

    def test_the_model_has_no_population_attribute(self):
        """Pins the typo itself, so a revert reads as a deliberate act."""
        assert not hasattr(PopulationData, "population"), (
            "PopulationData grew a `population` attribute; _get_population_map "
            "was written against one that never existed"
        )
        assert hasattr(PopulationData, "total_population")

    def test_a_national_row_is_not_a_county_population(self, db):
        """id=69's 82 must not become a divisor.

        The caller divides a county's pending-bill total by whatever this map
        yields for that entity's canonical name. 82 is not a population, and
        "National Government" is not a county.
        """
        _production_shape(db)

        mapping = _get_population_map(db)

        assert mapping.get("Nairobi") == NAIROBI_2019, (
            "the counties must be present — otherwise this test passes "
            "vacuously against the empty map it exists to catch"
        )
        assert "National Government" not in mapping
        assert ID_69 not in mapping.values()

    def test_the_latest_year_is_taken_per_entity_not_globally(self, db):
        """One county with a newer row must not hide every other county."""
        entities = _production_shape(db)
        db.add(
            PopulationData(
                entity_id=entities["nairobi"].id, year=2024, total_population=5_100_000
            )
        )
        db.commit()

        assert _get_population_map(db) == {
            "Nairobi": 5_100_000,  # its own newest year
            "Baringo": BARINGO_2019,  # not dropped for lacking a 2024 row
        }

    def test_a_broken_lookup_raises_instead_of_reporting_an_empty_map(self, db):
        """A silent fallback that certifies its own blindness.

        ``except Exception: return {}`` made "the query failed" and "the
        database holds no population" the same answer, which is how the
        AttributeError survived. An empty map must mean the table is empty.
        """
        _production_shape(db)
        db.execute(__import__("sqlalchemy").text("DROP TABLE population_data"))

        with pytest.raises(Exception) as caught:
            _get_population_map(db)

        assert "population_data" in str(caught.value).lower()

    def test_an_empty_table_still_yields_an_empty_map(self, db):
        """Absence is a legitimate answer; only a *failure* must raise."""
        _entity(db, "Nairobi", EntityType.COUNTY)
        db.commit()

        assert _get_population_map(db) == {}


class TestPendingBillsSaysWhyPerCapitaIsAbsent:
    """Withholding is a claim; the reader must be able to act on it."""

    def test_absent_per_capita_carries_a_reason(self, db):
        from main import _attach_per_capita

        _production_shape(db)
        counties = [{"county": "Nairobi", "amount": 1000.0}, {"county": "Turkana", "amount": 50.0}]

        _attach_per_capita(db, counties)

        nairobi, turkana = counties
        assert nairobi["per_capita"] == round(1000.0 / NAIROBI_2019, 2)
        assert nairobi["per_capita_absent_reason"] is None
        assert turkana["per_capita"] is None
        assert turkana["per_capita_absent_reason"] == "no_population_row_for_entity"

    def test_an_empty_map_is_distinguishable_from_a_missing_county(self, db):
        from main import _attach_per_capita

        _entity(db, "Nairobi", EntityType.COUNTY)
        db.commit()
        counties = [{"county": "Nairobi", "amount": 1000.0}]

        _attach_per_capita(db, counties)

        assert counties[0]["per_capita"] is None
        assert counties[0]["per_capita_absent_reason"] == "no_population_data"


class TestLatestNationalPopulation:
    """The fallback must not publish 82, or 2x Kenya, as Kenya."""

    def test_the_national_series_is_still_preferred(self, db):
        """The path that serves /population/latest today. Must stay correct."""
        _production_shape(db)
        db.add(
            PopulationData(entity_id=None, year=2025, total_population=WORLD_BANK_2025)
        )
        db.commit()

        assert latest_national_population(db) == (WORLD_BANK_2025, 2025)

    def test_82_is_never_published_as_kenyas_population(self, db):
        """Exactly production's rows with the World Bank series removed.

        Before this change the fallback took MAX(year) = 2026 and summed
        ``total_population`` there, which is id=69 alone: (82, 2026). A caller
        dividing by that produces per-capita figures ~580,000,000x too large.
        """
        _production_shape(db)

        assert latest_national_population(db) == (None, None)

    def test_the_county_sum_double_counted_the_national_row(self, db):
        """The case a county-count guard would have waved through.

        With id=69 gone, MAX(year) is 2019, which covers every county — and the
        sum is still wrong, because the filter is ``entity_id IS NOT NULL``
        rather than "county". On production that is 47,564,296 x 2 =
        95,128,592.
        """
        entities = _production_shape(db)
        db.query(PopulationData).filter(
            PopulationData.entity_id == entities["national"].id,
            PopulationData.year == 2026,
        ).delete()
        db.commit()

        total, year = latest_national_population(db)

        assert (total, year) == (None, None), (
            f"returned {total!r} for {year!r}; that sum includes the National "
            f"Government's own {NATIONAL_2019:,} alongside the county rows, so "
            f"it is not Kenya's population (on production: 95,128,592)"
        )

    def test_absence_is_returned_rather_than_zero(self, db):
        """An empty table must not read as a real zero."""
        assert latest_national_population(db) == (None, None)
