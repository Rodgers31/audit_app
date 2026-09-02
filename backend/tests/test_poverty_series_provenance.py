"""Poverty figures must come from a source, and cite the right one.

Issue #137 P7. ``POVERTY_SERIES`` was nine figures held as a Python constant
and inserted at confidence 0.85 — the surviving sibling of
``NATIONAL_GDP_SERIES``, the hardcoded constant that published GDP 15.4T and
an 82% debt-to-GDP ratio until it was pruned (tests/test_national_gdp_reconcile.py).

Three separate defects, each pinned below:

1. **A citation that does not resolve to the figure.** Every row cited one
   generic document — ``https://www.knbs.or.ke/economic-survey-2025/``, titled
   "KNBS Economic Survey 2025 & World Bank Poverty Data" — while the rows' own
   metadata named three DIFFERENT publications ("KNBS KIHBS 2021", "KNBS KIHBS
   2015/16 (adjusted for 2019 Census)", "World Bank Kenya Economic Update
   2024"). None of the three is that document. A citation that looks checkable
   and is wrong is worse than one that is absent.

2. **Years with no observation.** Rows were published for 2019 and 2024. The
   World Bank reports neither. Both carried the 2015 Gini (0.408); 2019 also
   carried the 2015 headcount (36.1), making that row the 2015 observation
   exactly, relabelled.

3. **A figure that contradicts the source it names.** The row labelled
   "KNBS KIHBS 2021" published headcount 36.1 — the World Bank's *2015* value.
   The 2021 observation is 38.6.

Observed pre-fix output, for the record::

    year=2024 headcount=33.40 extreme=8.60 gini=0.408 conf=0.85
    year=2021 headcount=36.10 extreme=10.20 gini=0.410 conf=0.85
    year=2019 headcount=36.10 extreme=8.50 gini=0.408 conf=0.85
    all three cite -> https://www.knbs.or.ke/economic-survey-2025/
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from models import Base, Country, PovertyIndex, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains import national_gdp
from seeding.domains.national_gdp import fetcher as gdp_fetcher
from seeding.types import DomainRunContext
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):  # pragma: no cover
    return "TEXT"


# The World Bank's real Kenya observations, verified live 2026-09-02.
# 2019 and 2024 are absent because the source does not report them.
WB_POVERTY = {
    2022: {"headcount": Decimal("39.8"), "gini": Decimal("0.385")},
    2021: {"headcount": Decimal("38.6"), "gini": Decimal("0.387")},
    2020: {"headcount": Decimal("42.9"), "gini": Decimal("0.362")},
    2015: {"headcount": Decimal("36.1"), "gini": Decimal("0.408")},
}


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as s:
        s.add(Country(name="Kenya", iso_code="KE", currency="KES",
                      timezone="Africa/Nairobi", default_locale="en-KE"))
        s.commit()
        yield s


def _run(session, monkeypatch, poverty=WB_POVERTY, gdp=None):
    monkeypatch.setattr(
        gdp_fetcher, "fetch_kenya_poverty", lambda *a, **kw: dict(poverty)
    )
    monkeypatch.setattr(
        gdp_fetcher, "fetch_national_gdp_kes", lambda *a, **kw: dict(gdp or {})
    )
    return national_gdp.run(
        session,
        SeedingSettings(),
        DomainRunContext(dry_run=False, since=None),
    )


class TestTheCitationResolvesToTheFigure:
    def test_rows_cite_the_indicator_they_were_read_from(self, session, monkeypatch):
        """RED before the fix: every row cited the Economic Survey 2025 page,
        which is not where any of the three figures came from."""
        _run(session, monkeypatch)
        rows = session.query(PovertyIndex).all()
        assert rows, "no poverty rows written — the assertion would be vacuous"
        for row in rows:
            doc = session.get(SourceDocument, row.source_document_id)
            assert doc is not None, f"{row.year} cites a document that is gone"
            assert "SI.POV" in (doc.url or ""), (
                f"the {row.year} poverty row cites {doc.url}, which is not the "
                "indicator the figure was read from"
            )


class TestOnlyObservedYearsPublish:
    def test_a_year_the_source_does_not_report_is_not_written(
        self, session, monkeypatch
    ):
        """RED before the fix: 2019 and 2024 were written unconditionally."""
        _run(session, monkeypatch)
        years = {r.year for r in session.query(PovertyIndex).all()}
        assert years == set(WB_POVERTY), f"published years {sorted(years)}"
        assert 2019 not in years and 2024 not in years

    def test_an_existing_unsourced_year_is_pruned(self, session, monkeypatch):
        """The half that matters in production, where 2019 and 2024 already
        exist: an upsert alone would leave them forever."""
        session.execute(
            PovertyIndex.__table__.insert().values(
                entity_id=None, year=2024,
                poverty_headcount_rate=Decimal("33.4"),
                extreme_poverty_rate=Decimal("8.6"),
                gini_coefficient=Decimal("0.408"),
                confidence=Decimal("0.85"),
            )
        )
        session.commit()
        _run(session, monkeypatch)
        assert session.query(PovertyIndex).filter_by(year=2024).first() is None

    def test_a_failed_fetch_prunes_nothing(self, session, monkeypatch):
        """POSITIVE CONTROL for the guard: last-known-good must survive an
        outage. Without this, an empty fetch would delete every real row."""
        session.execute(
            PovertyIndex.__table__.insert().values(
                entity_id=None, year=2021,
                poverty_headcount_rate=Decimal("38.6"),
                confidence=Decimal("0.95"),
            )
        )
        session.commit()

        def _boom(*a, **kw):
            raise RuntimeError("World Bank unreachable")

        monkeypatch.setattr(gdp_fetcher, "fetch_kenya_poverty", _boom)
        monkeypatch.setattr(gdp_fetcher, "fetch_national_gdp_kes", lambda *a, **k: {})
        national_gdp.run(session, SeedingSettings(), DomainRunContext(dry_run=False, since=None))
        assert session.query(PovertyIndex).filter_by(year=2021).first() is not None


class TestTheFiguresMatchTheSource:
    def test_the_2021_headcount_is_the_2021_observation(self, session, monkeypatch):
        """RED before the fix: 36.1, which is the World Bank's 2015 value,
        published under a row labelled "KNBS KIHBS 2021"."""
        _run(session, monkeypatch)
        row = session.query(PovertyIndex).filter_by(year=2021).one()
        assert row.poverty_headcount_rate == Decimal("38.6")

    def test_gini_is_stored_on_the_columns_scale(self, session, monkeypatch):
        """The World Bank reports 0-100 and the column holds 0-1. Getting this
        wrong publishes a Gini of 38.7."""
        _run(session, monkeypatch)
        for row in session.query(PovertyIndex).all():
            assert Decimal("0") < row.gini_coefficient < Decimal("1"), (
                f"{row.year} gini {row.gini_coefficient} is not on the 0-1 scale"
            )


class TestExtremePovertyIsAbsentNotSubstituted:
    def test_it_is_null_with_a_recorded_reason(self, session, monkeypatch):
        """The World Bank's SI.POV.DDAY ($2.15/day) reads ~45% for Kenya; the
        constant held 8.5-10.2, the national food-poverty rate. Substituting
        one for the other would move a published figure fivefold and call it a
        correction, so the column is null and says why."""
        _run(session, monkeypatch)
        rows = session.query(PovertyIndex).all()
        assert rows
        for row in rows:
            assert row.extreme_poverty_rate is None, (
                f"{row.year} published an extreme-poverty figure with no source"
            )
            assert "extreme_poverty_rate_absent_reason" in (row.meta or {}), (
                "the absence carries no machine-readable reason"
            )

    def test_an_existing_unsourced_extreme_value_is_cleared(
        self, session, monkeypatch
    ):
        session.execute(
            PovertyIndex.__table__.insert().values(
                entity_id=None, year=2021,
                poverty_headcount_rate=Decimal("36.1"),
                extreme_poverty_rate=Decimal("10.2"),
                gini_coefficient=Decimal("0.410"),
                confidence=Decimal("0.85"),
            )
        )
        session.commit()
        _run(session, monkeypatch)
        row = session.query(PovertyIndex).filter_by(year=2021).one()
        assert row.extreme_poverty_rate is None
        assert row.poverty_headcount_rate == Decimal("38.6")


class TestTheConstantIsGone:
    def test_no_hardcoded_poverty_series_remains(self):
        import inspect

        src = inspect.getsource(national_gdp)
        assert "POVERTY_SERIES = [" not in src, (
            "the hardcoded poverty constant is back"
        )
