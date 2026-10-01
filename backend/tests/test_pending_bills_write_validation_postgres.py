"""PostgreSQL persistence, reopen, dispatch ledger and source-shaped controls.

ORM DDL in owned synthetic schemas is not migrated-production proof.
"""
import argparse
import os
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from models import Base, Country, Entity, EntityType, IngestionJob, Loan
from seeding.domains.pending_bills.parser import parse_pending_bills_payload
from tests.test_pending_bills_write_validation import BAD, record, state, write


@pytest.fixture
def pg_engine():
    raw = os.environ.get("PENDING_BILLS_TEST_POSTGRES_URL")
    if not raw:
        pytest.skip("Requires an explicitly owned loopback PostgreSQL database")
    url = make_url(raw)
    assert url.host == "127.0.0.1" and url.get_backend_name() == "postgresql"
    assert not any(
        os.environ.get(k) for k in ("PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")
    )
    args = dict(hostaddr="127.0.0.1", sslmode="disable", gssencmode="disable")
    control = create_engine(url, connect_args=args)
    schema = "r9s1_" + uuid.uuid4().hex
    with control.begin() as c:
        c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        url, connect_args={**args, "options": f"-csearch_path={schema}"}
    )
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            db.add(
                Country(
                    iso_code="KEN",
                    name="Synthetic Kenya",
                    currency="KES",
                    timezone="Africa/Nairobi",
                    default_locale="en_KE",
                )
            )
            db.flush()
            db.add(
                Entity(
                    country_id=db.query(Country).one().id,
                    type=EntityType.NATIONAL,
                    canonical_name="National Government",
                    slug="national",
                )
            )
            db.commit()
        yield engine
    finally:
        engine.dispose()
        with control.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            assert (
                c.execute(
                    text("SELECT count(*) FROM pg_namespace WHERE nspname=:s"),
                    {"s": schema},
                ).scalar()
                == 0
            )
        control.dispose()


@pytest.mark.parametrize(
    "field", ["total_pending", "eligible_pending", "ineligible_pending"]
)
@pytest.mark.parametrize("amount", BAD)
def test_real_direct_refusal_commit_reopen_retry(pg_engine, field, amount):
    with Session(pg_engine) as db:
        assert write(db, [record()]) == (1, 0)
        db.commit()
        before = state(db)
        with pytest.raises(ValueError):
            write(
                db,
                [
                    record(total_pending=Decimal(25)),
                    record(category="state_corporation", **{field: amount}),
                ],
                source_url="https://example.invalid/correction.pdf",
                publisher="Changed publisher",
            )
        db.commit()  # Caller catches refusal then commits unrelated work.
    with Session(pg_engine) as db:
        assert state(db) == before
        assert write(db, [record(total_pending=Decimal(0))]) == (0, 1)
        db.commit()
    with Session(pg_engine) as db:
        from main import _published_pending_bills

        rows, totals = _published_pending_bills(db)
        assert [r[3] for r in rows] == [0]
        assert totals["national"] is None  # One component isn't a complete BROP.
        assert db.query(Loan).one().outstanding == 0


@pytest.mark.parametrize(
    "amount", [-1, "NaN", "Infinity", "-Infinity", True, False, [], {}]
)
def test_summary_dispatch_records_failure_not_clean_empty_success(pg_engine, amount):
    from seeding import cli, freshness
    from seeding.config import SeedingSettings
    import seeding.domains.pending_bills as domain

    settings = SeedingSettings(
        _env_file=None, live_pdf_fetch_enabled=False, parse_cache_enabled=False
    )
    payload = dict(
        summary={"total_national": amount},
        pending_bills=[],
        publication="treasury_brop_national_pending_bills",
        source_url="https://example.invalid/session1.pdf",
    )
    # Use the actual declaration constant, not a synthetic spell-alike.
    from services.publication_gate import NATIONAL_PENDING_BILLS_PUBLICATION

    payload["publication"] = NATIONAL_PENDING_BILLS_PUBLICATION
    args = argparse.Namespace(
        domain=["pending_bills"], all=False, since=None, dry_run=False
    )
    with patch.object(cli, "SessionLocal", sessionmaker(bind=pg_engine)), patch.object(
        domain.fetcher, "fetch_pending_bills_payload", return_value=payload
    ), patch.object(domain.fetcher, "fetch_county_payables_payload", return_value=None):
        cli.run_seed_command(args, settings)
    with Session(pg_engine) as db:
        job = db.query(IngestionJob).one()
        assert job.status.value != "completed" and job.errors
        assert job.items_created == 0 and job.items_updated == 0
        assert db.query(Loan).count() == 0
    freshness.reset("pending_bills")


def test_runtime_and_source_shaped_positive_controls(pg_engine):
    import main
    from config.settings import Settings
    from tests.test_pending_publication_completeness_adversarial import (
        _national_payload,
    )

    assert main.AUTO_SEEDER_ENABLED is False and main._WARMUP_ENABLED is False
    assert Settings(_env_file=None).REDIS_URL == ""
    print("RESOLVED: seeder=false warmup=false redis=empty dotenv_disabled=1")
    with pg_engine.connect() as c:
        print("POSTGRES:", c.execute(text("SELECT version()")).scalar())
        assert c.execute(text("SELECT inet_server_addr()::text")).scalar() is not None
    from services.publication_gate import NATIONAL_PENDING_BILLS_PUBLICATION

    with Session(pg_engine) as db:
        payload = _national_payload(sc=0, mda=200)
        parsed = parse_pending_bills_payload(payload)
        assert len(parsed) == 2
        assert write(
            db,
            parsed,
            publication=NATIONAL_PENDING_BILLS_PUBLICATION,
            source_url=payload["source_url"],
            source_title=payload["source_title"],
            publisher=payload["publisher"],
        ) == (2, 0)
        db.commit()
    with Session(pg_engine) as db:
        rows, totals = main._published_pending_bills(db)
        assert sorted(r[3] for r in rows) == [0, 200_000_000_000]
        assert totals["national"] == 200_000_000_000


def test_missing_required_total_and_late_flush_failure_preserve_committed_state(
    pg_engine,
):
    from sqlalchemy.exc import StatementError

    with Session(pg_engine) as db:
        write(db, [record()])
        db.commit()
        before = state(db)
        with pytest.raises(ValueError):
            write(db, [record(total_pending=None)])
        # A direct caller's non-JSON note fails after the first row and source
        # have actually changed. This exercises rollback, beyond preflight.
        with pytest.raises(StatementError):
            write(
                db,
                [
                    record(total_pending=Decimal(25)),
                    record(
                        category="state_corporation", reader_notes=[{"code": object()}]
                    ),
                ],
                source_url="https://example.invalid/correction.pdf",
                publisher="Changed publisher",
            )
        db.commit()
    with Session(pg_engine) as db:
        assert state(db) == before
        assert write(db, [record(eligible_pending=None, ineligible_pending=None)]) == (
            0,
            1,
        )
        db.commit()


@pytest.mark.parametrize(
    "amount", [-1, "NaN", "Infinity", "-Infinity", True, False, None, [], {}]
)
def test_county_invalid_batch_preserves_current_edition_and_source(pg_engine, amount):
    from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION
    from tests.test_pending_publication_completeness_adversarial import _county_payload
    from seeding.pdf_parsers import KENYAN_COUNTIES

    payload = _county_payload()
    kwargs = dict(
        source_url=payload["source_url"],
        source_title=payload["source_title"],
        publisher=payload["publisher"],
        publication=COUNTY_PENDING_BILLS_PUBLICATION,
        county_table=payload["county_table"],
    )
    with Session(pg_engine) as db:
        country = db.query(Country).one()
        for name in KENYAN_COUNTIES:
            db.add(
                Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name=f"{name} County",
                    slug=name.lower().replace(" ", "-"),
                )
            )
        db.commit()
        parsed = parse_pending_bills_payload(payload)
        assert write(db, parsed, **kwargs) == (47, 0)
        db.commit()
        before = state(db)
        from dataclasses import replace

        with pytest.raises(ValueError):
            write(
                db,
                [
                    replace(parsed[0], total_pending=Decimal(25)),
                    replace(parsed[1], total_pending=amount),
                ],
                **{**kwargs, "publisher": "Changed publisher"},
            )
        db.commit()
    with Session(pg_engine) as db:
        assert state(db) == before
        from main import _published_pending_bills

        rows, totals = _published_pending_bills(db)
        assert len(rows) == 47 and totals["county"] == 46_000_000
        # Genuine withheld county semantics remain source metadata, not a zero.
        withheld = _county_payload(withheld=True)
        records = parse_pending_bills_payload(withheld)
        kwargs["county_table"] = withheld["county_table"]
        assert write(db, records, **kwargs) == (0, 46)
        db.commit()
    with Session(pg_engine) as db:
        rows, totals = _published_pending_bills(db)
        assert len(rows) == 46 and totals["county"] is None
        assert totals["coverage"]["county_complete"] is False


@pytest.mark.parametrize("bad_half", ["national", "national_write", "county"])
def test_invalid_half_retains_valid_independent_half_and_partial_ledger(
    pg_engine, bad_half
):
    from seeding import cli, freshness
    from seeding.config import SeedingSettings
    import seeding.domains.pending_bills as domain
    from tests.test_pending_publication_completeness_adversarial import (
        _county_payload,
        _national_payload,
    )
    from seeding.pdf_parsers import KENYAN_COUNTIES

    national = _national_payload(sc=0, mda=200)
    county = _county_payload()
    if bad_half == "national":
        national["summary"]["total_national"] = "NaN"
    elif bad_half == "national_write":
        national["pending_bills"][0]["total_pending"] = "100000000000000000000"
    else:
        county.setdefault("summary", {})["total_county"] = "NaN"

    def fetch_national(*args):
        freshness.mark_live("pending_bills", detail="Synthetic fetched BROP")
        return national

    settings = SeedingSettings(
        _env_file=None, live_pdf_fetch_enabled=False, parse_cache_enabled=False
    )
    args = argparse.Namespace(
        domain=["pending_bills"], all=False, since=None, dry_run=False
    )
    with Session(pg_engine) as db:
        country_row = db.query(Country).one()
        for name in KENYAN_COUNTIES:
            db.add(
                Entity(
                    country_id=country_row.id,
                    type=EntityType.COUNTY,
                    canonical_name=f"{name} County",
                    slug=name.lower().replace(" ", "-"),
                )
            )
        db.commit()
    try:
        with patch.object(
            cli, "SessionLocal", sessionmaker(bind=pg_engine)
        ), patch.object(
            domain.fetcher, "fetch_pending_bills_payload", side_effect=fetch_national
        ), patch.object(
            domain.fetcher, "fetch_county_payables_payload", return_value=county
        ):
            cli.run_seed_command(args, settings)
        with Session(pg_engine) as db:
            job = db.query(IngestionJob).one()
            assert job.status.value == "completed_with_errors" and job.errors
            assert job.meta["source_mode"] == "partial"
            expected = 2 if bad_half == "county" else 47
            assert job.items_created == expected and job.items_updated == 0
            assert db.query(Loan).count() == expected
    finally:
        freshness.reset("pending_bills")
