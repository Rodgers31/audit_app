"""Exercise county edition serialization with real competing PostgreSQL sessions.

Requires SESSION2_POSTGRES_URL: localhost, empty audit_app_session2* database.
All identities, amounts and documents are synthetic test data. No production URL.
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if not __debug__:
    raise RuntimeError("Run without -O: this verification requires active assertions")
url = os.environ["SESSION2_POSTGRES_URL"]
parsed = urlparse(url)
assert parsed.scheme in {"postgresql", "postgresql+psycopg2"}
assert (
    not parsed.query and not parsed.fragment
), "Connection URL overrides are forbidden"
assert parsed.hostname in {"localhost", "127.0.0.1"}
assert parsed.path.startswith("/audit_app_session2")
os.environ["DATABASE_URL"] = url
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from models import Base, Country, Entity, EntityType, Loan
from seeding.domains.pending_bills.parser import PendingBillRecord
from seeding.domains.pending_bills.writer import write_pending_bills
from services.publication_gate import COUNTY_PENDING_BILLS_PUBLICATION

engine = create_engine(
    url, connect_args={"options": "-c statement_timeout=15000 -c lock_timeout=10000"}
)
inspector = inspect(engine)
assert set(inspector.get_schema_names()) - {"information_schema"} == {
    "public"
}, "Use a fresh database"
assert not any(
    (
        inspector.get_table_names(),
        inspector.get_view_names(),
        inspector.get_materialized_view_names(),
        inspector.get_sequence_names(),
        inspector.get_enums(),
    )
), "Use a fresh empty disposable database"
Base.metadata.create_all(engine)
with Session(engine) as db:
    db.add(
        Country(
            id=1,
            name="Kenya",
            iso_code="KEN",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en-KE",
        )
    )
    db.flush()
    db.add_all(
        [
            Entity(
                id=3,
                country_id=1,
                type=EntityType.COUNTY,
                canonical_name="Nairobi County",
                slug="nairobi-county",
            ),
            Entity(
                id=4,
                country_id=1,
                type=EntityType.COUNTY,
                canonical_name="Mombasa County",
                slug="mombasa-county",
            ),
        ]
    )
    db.commit()


def records(day, amount):
    year = int(day[:4])
    return [
        PendingBillRecord(
            entity_name=name,
            entity_type="county",
            category="county",
            fiscal_year=f"FY{year-1}/{str(year)[2:]}",
            total_pending=Decimal(amount),
            as_at=day,
            source_page=1,
            source_table="Synthetic test table",
        )
        # counties-literal-ok: Synthetic race fixtures in a required empty localhost test database; never a public ranking.
        for name in ("Mombasa County", "Nairobi County")
    ]


def write(db, day, amount, payload=None):
    return write_pending_bills(
        db,
        records(day, amount) if payload is None else payload,
        source_url="https://example.org/synthetic-edition.pdf",
        source_title=f"Synthetic test edition {day}",
        publication=COUNTY_PENDING_BILLS_PUBLICATION,
        county_table={"as_at": day},
    )


def state():
    with Session(engine) as db:
        return [
            (
                row.entity_id,
                row.outstanding,
                row.provenance["as_at"],
                row.provenance["publication"],
            )
            for row in db.query(Loan).order_by(Loan.entity_id)
        ]


def assert_state(day, amount):
    assert state() == [
        (eid, Decimal(amount), day, COUNTY_PENDING_BILLS_PUBLICATION) for eid in (3, 4)
    ]


with Session(engine) as db:
    write(db, "2026-06-30", "100")
    db.commit()


def competing(day, amount, started, pid):
    try:
        with Session(engine) as db:
            with db.begin():
                pid.append(db.scalar(text("select pg_backend_pid()")))
                started.set()
                write(db, day, amount)
        return "written"
    except ValueError as exc:
        assert "Stale county edition" in str(exc), str(exc)
        return "stale"


def race(
    first_day, first_amount, second_day, second_amount, *, rollback=False, expected
):
    # Close/rollback the lock owner before waiting for the worker on any failure.
    with ThreadPoolExecutor(max_workers=1) as pool, Session(engine) as first:
        first.begin()
        write(first, first_day, first_amount)
        started, pid = threading.Event(), []
        future = pool.submit(competing, second_day, second_amount, started, pid)
        assert started.wait(5), "Competing session did not start"
        deadline = time.monotonic() + 5
        blocked = False
        with engine.connect() as observer:
            while time.monotonic() < deadline:
                waiting = observer.execute(
                    text("select wait_event_type from pg_stat_activity where pid=:pid"),
                    {"pid": pid[0]},
                ).scalar()
                observer.commit()
                if waiting == "Lock":
                    blocked = True
                    break
                if future.done():
                    break
                time.sleep(0.01)
        assert (
            blocked and not future.done()
        ), "Second writer did not wait on the county lock"
        if rollback:
            first.rollback()
        else:
            first.commit()
        assert future.result(timeout=5) == expected


race("2027-06-30", "700", "2026-06-30", "200", expected="stale")
assert_state("2027-06-30", "700")
print("PASS: older writer blocks, then rejects after newer edition commits")
race("2028-06-30", "800", "2027-06-30", "750", rollback=True, expected="written")
assert_state("2027-06-30", "750")
print("PASS: rolled-back newer edition leaves prior edition eligible for correction")
race("2027-06-30", "760", "2027-06-30", "770", expected="written")
assert_state("2027-06-30", "770")
print("PASS: two same-date corrections serialize and the later correction persists")
race("2027-06-30", "780", "2028-06-30", "800", expected="written")
assert_state("2028-06-30", "800")
print("PASS: newer writer follows and replaces committed same-date correction")

before = state()
with Session(engine) as db:
    malformed = records("2028-06-30", "900")
    malformed[-1].reader_notes = [42]
    try:
        write(db, "2028-06-30", "900", malformed)
    except TypeError:
        pass
    else:
        raise AssertionError("Malformed late record was accepted")
    # Simulate the domain catching the error then committing its outer transaction.
    db.commit()
assert state() == before
print("PASS: late-record error rolls back the savepoint even if outer caller commits")
print(
    "PostgreSQL concurrency verification: five scenarios passed; four observed lock waits."
)
