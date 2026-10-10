"""Real bootstrap/lifespan and registered health HTTP, with inert native handlers."""
import asyncio
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading

import httpx
from sqlalchemy import text
from database import SessionLocal, engine
from models import Base, Country, Entity, EntityType
from services.county_identity import OFFICIAL_COUNTY_CODES
import bootstrap
import main


async def inert_scheduler():
    """Suppress unrelated scheduled transports; actual startup remains unchanged."""
    return None


main._setup_etl_scheduler = inert_scheduler

Base.metadata.create_all(engine)


def observe():
    with engine.connect() as db:
        return dict(
            counties=db.scalar(
                text("SELECT count(*) FROM entities WHERE type='COUNTY'")
            ),
            jobs=[
                list(r)
                for r in db.execute(
                    text(
                        "SELECT id,domain,status,finished_at FROM ingestion_jobs ORDER BY id"
                    )
                )
            ],
            claims=[
                list(map(str, r))
                for r in db.execute(
                    text("SELECT * FROM seeding_domain_claims ORDER BY id")
                )
            ],
        )


def references(mode):
    if mode == "empty":
        return
    with SessionLocal.begin() as db:
        country = Country(
            name="Kenya",
            iso_code="KEN" if mode != "wrong_country" else "ZZZ",
            currency="KES",
            timezone="Africa/Nairobi",
            default_locale="en_KE",
        )
        db.add(country)
        db.flush()
        for code, name in OFFICIAL_COUNTY_CODES.items():
            if mode in {"partial", "count_decoy"} and code == "047":
                continue
            db.add(
                Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name=name + " County"
                    if mode != "arbitrary"
                    else "Arbitrary " + code,
                    slug="owned-" + code,
                    meta={},
                )
            )
        if mode == "count_decoy":
            db.add(
                Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name="Unrecognized County",
                    slug="count-decoy",
                    meta={},
                )
            )
        if mode == "duplicate":
            db.add(
                Entity(
                    country_id=country.id,
                    type=EntityType.COUNTY,
                    canonical_name="Nairobi City County",
                    slug="duplicate-nairobi",
                    meta={},
                )
            )
        if mode == "blank_slug":
            db.flush()
            db.query(Entity).filter(Entity.slug == "owned-047").update({"slug": ""})


async def health(path="/health/ready"):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url="http://testserver"
    ) as client:
        response = await client.get(path)
        return dict(code=response.status_code, body=response.json())


def writer():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "seeding.cli",
            "seed",
            "--domain",
            "audits",
            "--no-dry-run",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )
    while True:
        if not select.select([proc.stdout], [], [], 15)[0]:
            raise RuntimeError("Native writer entry barrier timed out")
        line = proc.stdout.readline()
        print("WRITER_LOG", line.rstrip(), flush=True)
        if line.strip() == "WRITER_ENTERED":
            return proc
        if not line:
            raise RuntimeError(
                f"Native writer exited before entry: {proc.wait(timeout=5)}"
            )


async def with_writer(mode):
    references(mode)
    proc = writer()
    try:
        before = observe()
        await asyncio.wait_for(main._startup_sequence(), 15)
        first = await health()
        during = observe()
        # Only the real CLI may finish/release this owned synthetic writer.
        log, _ = proc.communicate("complete\n", timeout=15)
        print("WRITER_TERMINAL", proc.returncode, log, flush=True)
        if proc.returncode != 0:
            raise RuntimeError("Native writer did not complete successfully")
        finished = observe()
        await asyncio.wait_for(main._startup_sequence(), 15)
        return dict(
            first=first,
            before=before,
            during=during,
            finished=finished,
            second=await health(),
            after=observe(),
            live=await health("/health/live"),
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


async def lifespan_control(mode):
    references("valid")
    original = main._startup_sequence
    completed = asyncio.Event()

    async def observed_startup():
        try:
            await original()
        finally:
            completed.set()

    main._startup_sequence = observed_startup
    async with main._app_lifespan(main.app):
        await asyncio.wait_for(completed.wait(), 15)
        first = await health()
    shutdown = await health()
    completed.clear()
    if mode == "unavailable":
        main.DATABASE_AVAILABLE = False
        try:
            async with main._app_lifespan(main.app):
                raise AssertionError("Unavailable database entered lifespan")
        except RuntimeError:
            pass
        return dict(first=first, second=await health(), shutdown=shutdown)
    if mode == "db_failure":

        def unavailable_session():
            raise RuntimeError("inert DB connection unavailable; secret=must-not-leak")

        bootstrap.SessionLocal = unavailable_session
    elif mode == "check_failure":
        import database

        def broken_check_session():
            raise RuntimeError(
                "inert verification connection failure; secret=must-not-leak"
            )

        database.SessionLocal = broken_check_session
    elif mode == "exception":

        def broken_country(session):
            raise RuntimeError("inert bootstrap exception; secret=must-not-leak")

        bootstrap._ensure_country = broken_country
    elif mode in {"no_data", "malformed_fixture"}:
        with engine.begin() as db:
            db.execute(text("DELETE FROM entities"))
        bootstrap.COUNTY_DATA_PATH = (
            Path(os.environ["SEED_STORAGE_PATH"]) / "owned_counties.json"
        )
        if mode == "malformed_fixture":
            bootstrap.COUNTY_DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            bootstrap.COUNTY_DATA_PATH.write_text("{malformed")
    elif mode in {"cancel", "cancel_check"}:
        entered, release = threading.Event(), threading.Event()
        original_probe = bootstrap._seed_run_in_flight

        def blocked_probe(session):
            entered.set()
            if not release.wait(15):
                raise RuntimeError("Owned cancellation barrier timed out")
            return original_probe(session)

        if mode == "cancel":
            bootstrap._seed_run_in_flight = blocked_probe
        else:
            original_check = main._required_references_available

            def blocked_check():
                entered.set()
                if not release.wait(15):
                    raise RuntimeError("Owned reference-check barrier timed out")
                return original_check()

            main._required_references_available = blocked_check
    async with main._app_lifespan(main.app):
        immediate = await health()
        live = await health("/health/live")
        if mode in {"cancel", "cancel_check"}:
            if not await asyncio.to_thread(entered.wait, 10):
                raise RuntimeError("Real bootstrap did not reach cancellation barrier")
        else:
            await asyncio.wait_for(completed.wait(), 15)
        second = await health()
    if mode in {"cancel", "cancel_check"}:
        release.set()
        # Join owned executor work before inspecting/closing the database.
        await asyncio.get_running_loop().shutdown_default_executor()
    return dict(
        first=first,
        immediate=immediate,
        second=second,
        shutdown=shutdown,
        final=await health(),
        live=live,
        state=observe(),
    )


async def prewarm_liveness():
    from sqlalchemy import event

    references("valid")
    entered, release, live_received = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    failures = []
    completed = asyncio.Event()
    original = main._startup_sequence

    def witness():
        if not entered.wait(10):
            failures.append("prewarm did not enter")
        elif not live_received.wait(3):
            failures.append("LIVENESS_BLOCKED_BY_PREWARM")
        release.set()

    def gate(connection, cursor, statement, parameters, context, executemany):
        if statement.strip() == "SELECT 1" and not entered.is_set():
            entered.set()
            if not release.wait(10):
                raise RuntimeError("Owned prewarm barrier was not released")

    async def observed_startup():
        try:
            await original()
        finally:
            completed.set()

    main._startup_sequence = observed_startup
    event.listen(engine, "before_cursor_execute", gate)
    thread = threading.Thread(target=witness)
    thread.start()
    try:
        async with main._app_lifespan(main.app):
            if not await asyncio.to_thread(entered.wait, 10):
                raise RuntimeError("Actual prewarm query never entered")
            live = await health("/health/live")
            live_received.set()
            await asyncio.to_thread(thread.join, 10)
            await asyncio.wait_for(completed.wait(), 15)
            ready = await health()
        return dict(failures=failures, live=live, ready=ready, shutdown=await health())
    finally:
        release.set()
        await asyncio.to_thread(thread.join, 10)
        if thread.is_alive():
            raise RuntimeError("Owned prewarm witness did not stop")
        event.remove(engine, "before_cursor_execute", gate)


async def run():
    mode = sys.argv[1]
    if mode == "prewarm":
        result = await prewarm_liveness()
    else:
        result = await (
            lifespan_control(mode[5:])
            if mode.startswith("life_")
            else with_writer(mode)
        )
    print("READINESS_RESULT " + json.dumps(result, default=str), flush=True)


try:
    asyncio.run(run())
finally:
    engine.dispose()
