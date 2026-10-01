"""Execute Kenya source identity/refusal at the real PostgreSQL boundary.

Set AUDIT_TEST_POSTGRES_URL to an owned disposable loopback database. These
fixtures use ORM DDL, not production migration state or publisher verification.
"""
from contextlib import nullcontext
from datetime import datetime, timezone
from decimal import Decimal
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from models import Base, Country, DocumentType, GDPData, PopulationData, PovertyIndex, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains import national_gdp as domain
from seeding.types import DomainRunContext


SPECS = [
    (domain._ensure_gdp_source_document,
     "https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN",
     "World Bank", "World Bank — Kenya GDP, current LCU (NY.GDP.MKTP.CN)",
     {"seeding_domain": "national_gdp", "indicator": "NY.GDP.MKTP.CN"}),
    (domain._ensure_poverty_source_document,
     "https://api.worldbank.org/v2/country/KEN/indicator/SI.POV.NAHC",
     "World Bank", "World Bank — Kenya poverty headcount at national poverty "
     "lines (SI.POV.NAHC) and Gini index (SI.POV.GINI)",
     {"seeding_domain": "national_gdp", "indicators": ["SI.POV.NAHC", "SI.POV.GINI"]}),
    (domain._ensure_source_document,
     "https://www.knbs.or.ke/economic-survey-2025/", "KNBS / World Bank",
     "KNBS Economic Survey 2025 & World Bank Poverty Data",
     {"seeding_domain": "national_gdp"}),
]


@pytest.fixture
def pg():
    address = os.environ.get("AUDIT_TEST_POSTGRES_URL")
    if not address:
        pytest.skip("Set AUDIT_TEST_POSTGRES_URL to owned disposable PostgreSQL")
    url = make_url(address)
    assert url.get_backend_name() == "postgresql" and url.host == "127.0.0.1"
    assert url.port and url.port != 5432
    pin = dict(hostaddr="127.0.0.1", sslmode="disable", gssencmode="disable", connect_timeout=5)
    schema = "gdp_source_416_" + uuid4().hex
    admin = create_engine(url, connect_args=pin)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={**pin, "options": f"-csearch_path={schema}"})
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            assert conn.execute(text("SELECT count(*) FROM pg_namespace WHERE nspname=:s"), {"s": schema}).scalar() == 0
        admin.dispose()


def country(id=1, iso="KEN", name="Kenya", currency="KES"):
    return Country(id=id, iso_code=iso, name=name, currency=currency,
                   timezone="Africa/Nairobi", default_locale="en_KE")


def document(spec, **overrides):
    _, url, publisher, title, meta = spec
    return SourceDocument(country_id=1, publisher=publisher, title=title,
                          url=url, fetch_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                          doc_type=DocumentType.REPORT, meta=dict(meta), **overrides)


def snapshot(db):
    return db.execute(text("SELECT row_to_json(s)::text FROM source_documents s ORDER BY id")).scalars().all()


@pytest.mark.parametrize("spec", SPECS, ids=["gdp", "poverty", "legacy_poverty"])
@pytest.mark.parametrize("kenya_id,foreign_id,iso", [(1, None, "KEN"), (1, 2, "KEN"), (9, 1, "KEN"), (7, 2, "KE")])
def test_first_source_uses_kenya_and_survives_reopen_and_retry(pg, spec, kenya_id, foreign_id, iso):
    helper, url, publisher, title, meta = spec
    with Session(pg) as db:
        db.add(country(kenya_id, iso))
        if foreign_id:
            db.add(country(foreign_id, "UGA", "Uganda", "UGX"))
        db.commit()
        doc = helper(db)
        assert (doc.country_id, doc.url, doc.publisher, doc.title, doc.meta) == (kenya_id, url, publisher, title, meta)
        assert doc.doc_type == DocumentType.REPORT and doc.file_path is None and doc.md5 is None
        doc_id = doc.id
        db.commit()
    with Session(pg) as db:
        before = snapshot(db)
        assert helper(db).id == doc_id
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before
        assert db.get(SourceDocument, doc_id).country.iso_code == iso


@pytest.mark.parametrize("spec", SPECS, ids=["gdp", "poverty", "legacy_poverty"])
@pytest.mark.parametrize("countries", [[], [country(2, "UGA", "Uganda", "UGX")],
    [country(1, "KEN", "Uganda")], [country(1, "KEN", "Kenya", "USD")],
    [country(1, "ken")], [country(1, "XXX")],
    [country(1), country(2, "KE")], [country(1), country(2, "UGA", "Kenya", "UGX")]],
    ids=["absent", "foreign_only", "wrong_name", "wrong_currency", "lowercase_code", "wrong_code", "aliases_conflict", "name_conflict"])
def test_country_refusal_creates_nothing_even_if_caller_commits(pg, spec, countries):
    # Build fresh ORM instances: parameter values must not retain session state.
    with Session(pg) as db:
        for c in countries:
            db.add(country(c.id, c.iso_code, c.name, c.currency))
        db.commit()
        with pytest.raises(ValueError, match="Kenya"):
            spec[0](db)
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == []


@pytest.mark.parametrize("spec", SPECS, ids=["gdp", "poverty", "legacy_poverty"])
@pytest.mark.parametrize("bad", [None, "foreign", "publisher", "title", "type", "metadata", "indicator", "domain", "duplicate"])
def test_existing_document_is_reused_only_when_identity_matches(pg, spec, bad):
    with Session(pg) as db:
        db.add_all([country(), country(2, "UGA", "Uganda", "UGX")]); db.flush()
        doc = document(spec, id=1823)
        doc.meta = {**doc.meta, "publication_date": "2024-12-31", "shared": ["preserve"]}
        if bad == "foreign": doc.country_id = 2
        if bad == "publisher": doc.publisher = "Foreign Bureau"
        if bad == "title": doc.title = "World Bank population SP.POP.TOTL"
        if bad == "type": doc.doc_type = DocumentType.AUDIT
        if bad == "metadata": doc.meta = ["malformed"]
        if bad == "indicator": doc.meta = {**doc.meta, "indicator": "SP.POP.TOTL", "indicators": ["SP.POP.TOTL"]}
        if bad == "domain": doc.meta = {**doc.meta, "seeding_domain": "population"}
        db.add(doc)
        if bad == "duplicate": db.add(document(spec, id=2541))
        db.commit(); before = snapshot(db)
        if bad:
            with pytest.raises(ValueError, match="source"):
                spec[0](db)
        else:
            assert spec[0](db).id == 1823
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before


@pytest.mark.parametrize("spec", SPECS, ids=["gdp", "poverty", "legacy_poverty"])
@pytest.mark.parametrize("key,value", [
    ("country", "UGA"), ("country_id", 2), ("country_id", True), ("country_id", 1.0),
    ("country_code", "UGA"), ("iso_code", "UGA"), ("currency", "USD"),
    ("source", "Foreign Bureau"), ("publisher", "Foreign Bureau"),
    ("measure", "GDP, current USD"), ("scope", "county"),
    ("dataset_id", "SP.POP.TOTL"), ("entity_id", 1), ("units", "millions"),
])
def test_optional_source_declarations_cannot_contradict_identity(pg, spec, key, value):
    with Session(pg) as db:
        db.add(country()); db.flush()
        doc = document(spec, id=1823)
        doc.meta = {**doc.meta, key: value}
        db.add(doc); db.commit(); before = snapshot(db)
        with pytest.raises(ValueError, match="source"):
            spec[0](db)
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before


@pytest.mark.parametrize("spec", SPECS, ids=["gdp", "poverty", "legacy_poverty"])
def test_coherent_optional_source_declarations_are_preserved(pg, spec):
    with Session(pg) as db:
        db.add(country()); db.flush()
        doc = document(spec, id=1823)
        is_gdp = spec[0] is domain._ensure_gdp_source_document
        doc.meta = {**doc.meta, "country": "Kenya", "country_id": 1,
            "country_code": "KEN", "iso_code": "KE", "currency": "KES",
            "source": spec[2], "publisher": spec[2], "scope": "national",
            "entity_id": None, "units": "LCU" if is_gdp else "percent and Gini 0-1",
            "measure": "GDP, current KES" if is_gdp else "Poverty headcount at national poverty lines and Gini index"}
        if spec[0] is not domain._ensure_source_document:
            doc.meta["dataset_id"] = "NY.GDP.MKTP.CN" if is_gdp else "SI.POV.NAHC"
        db.add(doc); db.commit(); before = snapshot(db)
        assert spec[0](db).id == 1823
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before


def run_fixture(db, tmp_path, monkeypatch):
    monkeypatch.setattr(domain, "create_http_client", lambda settings: nullcontext(None))
    monkeypatch.setattr(domain.fetcher, "fetch_national_gdp_kes", lambda *args: {2024: Decimal("0")})
    monkeypatch.setattr(domain.fetcher, "fetch_kenya_poverty", lambda *args: {2022: {"headcount": Decimal("0"), "gini": None}})
    return domain.run(db, SeedingSettings(storage_path=tmp_path, cache_path=tmp_path,
        http_cache_enabled=False), DomainRunContext(since=None, dry_run=False))


@pytest.mark.parametrize("conflict", ["country", "gdp", "poverty", None])
def test_domain_refuses_atomically_and_preserves_shared_documents(pg, tmp_path, monkeypatch, conflict):
    with Session(pg) as db:
        db.add(country(1, "UGA", "Uganda", "UGX") if conflict == "country" else country())
        db.flush()
        for id in (1823, 2541):
            db.add(SourceDocument(id=id, country_id=1, publisher="Shared source",
                title="Shared fixture", url=f"https://example.invalid/{id}",
                fetch_date=datetime(2024, 1, 1), doc_type=DocumentType.REPORT,
                meta={"shared": [id]}))
        if conflict in ("gdp", "poverty"):
            doc = document(SPECS[0 if conflict == "gdp" else 1], id=100)
            doc.publisher = "Wrong publisher"; db.add(doc)
        db.add(GDPData(id=50, entity_id=None, year=2020, gdp_value=Decimal("12"), currency="KES", source_document_id=1823))
        db.add(PopulationData(id=79, entity_id=None, year=2019,
            total_population=51_202_827, source_document_id=1823,
            meta={"source": "World Bank", "synthetic_preservation_control": True}))
        db.commit(); before = snapshot(db)
        population_before = db.execute(text("SELECT row_to_json(p)::text FROM population_data p")).scalars().all()
        result = run_fixture(db, tmp_path, monkeypatch)
        db.commit()
    with Session(pg) as db:
        assert db.execute(text("SELECT row_to_json(p)::text FROM population_data p")).scalars().all() == population_before
        if conflict:
            assert result.errors and result.items_created == result.items_updated == 0
            assert snapshot(db) == before
            assert [(r.id, r.year, r.gdp_value, r.source_document_id) for r in db.scalars(select(GDPData))] == [(50, 2020, Decimal("12"), 1823)]
            assert db.query(PovertyIndex).count() == 0
        else:
            assert result.errors == [] and result.items_created == 2
            gdp = db.scalar(select(GDPData).where(GDPData.year == 2024))
            poverty = db.scalar(select(PovertyIndex))
            assert gdp.gdp_value == poverty.poverty_headcount_rate == 0
            assert poverty.gini_coefficient is None and poverty.extreme_poverty_rate is None
            for row in (gdp, poverty):
                assert db.get(SourceDocument, row.source_document_id).country_id == 1
            assert snapshot(db)[-2:] == before  # shared IDs are above new sources
            repeat = run_fixture(db, tmp_path, monkeypatch)
            assert repeat.errors == [] and repeat.items_created == repeat.items_updated == 0
            db.commit()


def test_late_source_refusal_rolls_back_updates_pruning_and_allows_corrected_retry(pg, tmp_path, monkeypatch):
    with Session(pg) as db:
        db.add(country()); db.flush()
        gdp_doc = document(SPECS[0], id=1823)
        poverty_doc = document(SPECS[1], id=2541)
        poverty_doc.country_id = 1
        poverty_doc.publisher = "Conflicting publisher"
        # Keep the baseline's obsolete first helper from masking the late
        # source conflict with its separate multiple-country exception.
        db.add_all([gdp_doc, poverty_doc, document(SPECS[2], id=900)]); db.flush()
        db.add_all([GDPData(id=50, year=2024, gdp_value=12, currency="KES", source_document_id=1823),
                    GDPData(id=51, year=2025, gdp_value=20, currency="KES", source_document_id=1823)])
        db.commit()
        before = snapshot(db)
        # A caller-owned pending edit is outside the domain savepoint.
        db.add(country(9, "UGA", "Uganda", "UGX"))
        result = run_fixture(db, tmp_path, monkeypatch)
        assert result.errors and result.items_created == result.items_updated == 0
        db.commit()
    with Session(pg) as db:
        assert snapshot(db) == before
        assert [(r.year, r.gdp_value) for r in db.scalars(select(GDPData).order_by(GDPData.year))] == [(2024, Decimal("12")), (2025, Decimal("20"))]
        assert db.get(Country, 9).iso_code == "UGA"
        assert db.query(PovertyIndex).count() == 0
        # Synthetic fixture correction only: the writer itself never relabels.
        db.get(SourceDocument, 2541).publisher = "World Bank"
        db.commit()
        retry = run_fixture(db, tmp_path, monkeypatch)
        assert retry.errors == [] and retry.items_created == retry.items_updated == 1
        db.commit()
    with Session(pg) as db:
        assert [(r.year, r.gdp_value) for r in db.scalars(select(GDPData))] == [(2024, Decimal("0"))]
        assert db.scalar(select(PovertyIndex)).source_document_id == 2541
