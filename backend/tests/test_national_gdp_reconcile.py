"""GDP seeder reconciliation (audit §3.1 — the stale-row half of the fix).

The GDP code fix (World Bank source, IMF headline ratio) was correct, but
production still served GDP = 15.4T because a stale 2025 row (the old
hardcoded NATIONAL_GDP_SERIES value) survived in the DB and — being the
newest year — out-ranked the real latest World Bank value in every
`order_by(year.desc())` lookup. The seeder only upserted; it never pruned.

This locks in that the national_gdp domain now reconciles the NULL-entity
GDP series to the authoritative World Bank fetch: years the source no longer
provides are deleted, so a fabricated future year can't re-inflate GDP. A
failed fetch must NOT prune (last-known-good is kept).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterator

import pytest
from models import Base, Country, GDPData
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


@pytest.fixture()
def sqlite_session(tmp_path) -> Iterator[Session]:
    engine = create_engine(f"sqlite:///{tmp_path/'gdp.db'}")
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    session.add(
        Country(
            id=1,
            iso_code="KEN",
            name="Kenya",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
    )
    # A correct latest-actual (2024) AND a stale 2025 = 15.4T leftover.
    session.add(
        GDPData(entity_id=None, year=2024, gdp_value=Decimal("16224478000000"), currency="KES")
    )
    session.add(
        GDPData(entity_id=None, year=2025, gdp_value=Decimal("15400000000000"), currency="KES")
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _settings(tmp_path) -> SeedingSettings:
    return SeedingSettings(
        storage_path=tmp_path / "storage",
        cache_path=tmp_path / "cache",
        log_path=tmp_path / "logs" / "seed.log",
        retry_backoff=0.01,
        max_retries=1,
    )


def _latest_null_gdp(session) -> GDPData:
    return (
        session.query(GDPData)
        .filter(GDPData.entity_id.is_(None))
        .order_by(GDPData.year.desc())
        .first()
    )


def test_prunes_stale_future_year_so_latest_is_correct(sqlite_session, tmp_path, monkeypatch):
    # World Bank publishes through 2024 only — no 2025.
    monkeypatch.setattr(
        gdp_fetcher,
        "fetch_national_gdp_kes",
        lambda client, settings: {2023: 15033610000000, 2024: 16224478000000},
    )

    national_gdp.run(sqlite_session, _settings(tmp_path), DomainRunContext(since=None, dry_run=False))
    sqlite_session.commit()

    years = sorted(
        r.year
        for r in sqlite_session.query(GDPData).filter(GDPData.entity_id.is_(None)).all()
    )
    assert 2025 not in years, "stale 2025 = 15.4T row must be pruned"
    assert _latest_null_gdp(sqlite_session).year == 2024
    assert float(_latest_null_gdp(sqlite_session).gdp_value) == 16224478000000.0


def test_historical_years_below_range_are_preserved(sqlite_session, tmp_path, monkeypatch):
    """A degraded fetch (fixture fallback, fewer years) must NOT delete the
    deep World Bank history already in the DB — only fabricated FUTURE years.
    """
    from decimal import Decimal as _D

    # The DB has deep history (2010) the fallback fixture doesn't list.
    sqlite_session.add(
        GDPData(entity_id=None, year=2010, gdp_value=_D("4000000000000"), currency="KES")
    )
    sqlite_session.commit()

    # Live WB unavailable → fetcher returns only the fixture's recent years.
    monkeypatch.setattr(
        gdp_fetcher,
        "fetch_national_gdp_kes",
        lambda client, settings: {2024: 16224478000000},
    )
    national_gdp.run(sqlite_session, _settings(tmp_path), DomainRunContext(since=None, dry_run=False))
    sqlite_session.commit()

    years = sorted(
        r.year
        for r in sqlite_session.query(GDPData).filter(GDPData.entity_id.is_(None)).all()
    )
    assert 2010 in years, "deep history must NOT be pruned on a short fetch"
    assert 2025 not in years, "fabricated future year must still be pruned"


def test_failed_fetch_keeps_existing_rows(sqlite_session, tmp_path, monkeypatch):
    # Total outage: fetcher raises → run() keeps whatever exists, prunes nothing.
    def _boom(client, settings):
        raise RuntimeError("World Bank + fixture both unavailable")

    monkeypatch.setattr(gdp_fetcher, "fetch_national_gdp_kes", _boom)

    national_gdp.run(sqlite_session, _settings(tmp_path), DomainRunContext(since=None, dry_run=False))
    sqlite_session.commit()

    years = sorted(
        r.year
        for r in sqlite_session.query(GDPData).filter(GDPData.entity_id.is_(None)).all()
    )
    # Nothing pruned on failure — both rows survive (last-known-good).
    assert years == [2024, 2025]
