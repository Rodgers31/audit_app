"""Federal response stays fresh across invalidation and avoids source metadata."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Event

from sqlalchemy import event

import main
from cache import invalidation
from models import Audit, Entity, EntityType, FiscalPeriod, Severity


def test_late_federal_fill_cannot_repopulate_the_invalidated_cache(
    db_session, monkeypatch, tmp_path
):
    """A load begun before invalidation may finish, but the next read is fresh."""
    marker = tmp_path / "federal-cache-generation"
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(marker))
    monkeypatch.setattr(invalidation, "_seen", None)
    monkeypatch.setattr(invalidation, "_seen_initialised", False)
    monkeypatch.setattr(main, "get_db", lambda: iter((db_session,)))

    entered = Event()
    release = Event()
    version = ["before"]
    original_meta = main._response_meta

    def gated_meta(*args, **kwargs):
        observed = version[0]
        if observed == "before":
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("federal load was not released")
        return {**original_meta(*args, **kwargs), "fixture_version": observed}

    monkeypatch.setattr(main, "_response_meta", gated_meta)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(lambda: asyncio.run(main._federal_audits_payload()))
        try:
            assert entered.wait(timeout=5), "the first load did not reach its output boundary"
            invalidation.invalidate_all()
            version[0] = "after"
        finally:
            release.set()
        assert first.result(timeout=5)["_meta"]["fixture_version"] == "before"

    refreshed = asyncio.run(main._federal_audits_payload())
    assert refreshed["_meta"]["fixture_version"] == "after"


def test_main_cached_loader_cannot_refill_after_generation_changes(
    monkeypatch, tmp_path
):
    """The main decorator's other routes share the same late-fill invariant."""
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "shared-generation"))
    monkeypatch.setattr(invalidation, "_seen", None)
    monkeypatch.setattr(invalidation, "_seen_initialised", False)
    entered = Event()
    release = Event()
    version = ["before"]

    @main.cached(key_prefix="review:late-fill", ttl=3600)
    async def endpoint():
        observed = version[0]
        if observed == "before":
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("cached load was not released")
        return {"version": observed}

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(lambda: asyncio.run(endpoint()))
        try:
            assert entered.wait(timeout=5)
            invalidation.invalidate_all()
            version[0] = "after"
        finally:
            release.set()
        assert first.result(timeout=5) == {"version": "before"}

    assert asyncio.run(endpoint()) == {"version": "after"}


def test_federal_report_source_does_not_select_unused_document_metadata(
    client, db_session, seed_country, seed_source_doc
):
    ministry = Entity(
        id=801,
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Source Projection",
        slug="ministry-source-projection",
    )
    period = FiscalPeriod(
        id=801,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    seed_source_doc.meta = {"private_reconciliation": "x" * 64_000}
    db_session.add_all([ministry, period])
    db_session.flush()
    db_session.add(
        Audit(
            entity_id=ministry.id,
            period_id=period.id,
            finding_text="Reported audit finding",
            severity=Severity.WARNING,
            source_document_id=seed_source_doc.id,
            page_ref="p.4",
        )
    )
    db_session.commit()

    statements = []
    engine = db_session.get_bind().engine

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get("/api/v1/audits/federal")
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200, response.text
    assert response.json()["report_title"] == seed_source_doc.title
    report_reads = [
        s
        for s in statements
        if "FROM source_documents JOIN audits" in s
        and "ORDER BY fiscal_periods.start_date DESC" in s
    ]
    assert len(report_reads) == 1
    assert "source_documents.metadata" not in report_reads[0].split(
        "FROM source_documents", 1
    )[0]
