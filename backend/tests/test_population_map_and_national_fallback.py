"""National population fallback controls using the historical #190 row shape.

The synthetic fixture includes county census rows, a national census row,
an unsourced national row of 82 people, and optionally the World Bank series.
The national series must be preferred; without it, these incomplete county
rows must not produce 82 or a double-counted national population.

The pending-bills population-map and per-capita helpers were removed after
that API switched exclusively to published Loan rows (#321). These tests
retain the separate, live ``latest_national_population`` contract. Historical
row IDs and figures below describe the fixture, not current production state.
"""

from __future__ import annotations

from typing import Iterator

import pytest
from models import Base, Country, Entity, EntityType, PopulationData
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from services.population import latest_national_population


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover - dialect shim
    return "TEXT"


# Historical fixture figures; not a claim about current production data.
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
    """The historical row shape, minus the World Bank series.

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


class TestLatestNationalPopulation:
    """The fallback must not publish 82, or 2x Kenya, as Kenya."""

    def test_the_national_series_is_still_preferred(self, db):
        """The live service must still prefer the national series."""
        _production_shape(db)
        db.add(
            PopulationData(entity_id=None, year=2025, total_population=WORLD_BANK_2025)
        )
        db.commit()

        assert latest_national_population(db) == (WORLD_BANK_2025, 2025)

    def test_82_is_never_published_as_kenyas_population(self, db):
        """Historical fixture rows with the World Bank series removed.

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
        rather than "county". In the historical reproduction that was 47,564,296 x 2 =
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
            f"it is not Kenya's population (historical reproduction: 95,128,592)"
        )

    def test_absence_is_returned_rather_than_zero(self, db):
        """An empty table must not read as a real zero."""
        assert latest_national_population(db) == (None, None)
