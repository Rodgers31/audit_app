"""Execute the SQLite JSON invalidation branch, independently of PG fixtures."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from models import SourceDocument, DocumentType, DocumentStatus
from seeding.native_report_authority import KEY, DOMAINS, persist_native_report
from seeding.types import DomainRunContext


@pytest.fixture
def sqlite_source():
    engine = create_engine("sqlite://")
    SourceDocument.__table__.create(engine)
    with Session(engine) as db:
        row = SourceDocument(country_id=1, publisher="Existing publisher", title="Retained source",
            url="https://cob.go.ke/retained.pdf", doc_type=DocumentType.REPORT,
            status=DocumentStatus.FAILED, fetch_date=datetime.now(timezone.utc))
        db.add(row)
        db.commit()
        yield db, row
    engine.dispose()


@pytest.mark.parametrize("domain", list(DOMAINS))
@pytest.mark.parametrize("metadata", [None, {}, {"unrelated": "x" * 65536},
    {KEY: None}, {KEY: {}}, {KEY: {"sibling": {"extraction_id": 9}}}])
def test_sqlite_absent_binding_preserves_noop_metadata(sqlite_source, domain, metadata):
    db, row = sqlite_source
    row.meta = deepcopy(metadata)
    db.commit()
    writes = []
    def observe(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("UPDATE SOURCE_DOCUMENTS"):
            writes.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", observe)
    try:
        persist_native_report(db, row, None, context=DomainRunContext(None, False), domain=domain)
        assert "meta" not in row.__dict__
        db.commit()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", observe)
    assert not writes
    assert db.scalar(select(SourceDocument.meta).where(SourceDocument.id == row.id)) == metadata


@pytest.mark.parametrize("value", [None, False, 0, "", {}, {"extraction_id": 7}])
@pytest.mark.parametrize("domain", list(DOMAINS))
def test_sqlite_present_falsy_and_stale_bindings_are_removed(sqlite_source, domain, value):
    db, row = sqlite_source
    original = {"unrelated": {"large": "x" * 65536}, KEY: {"sibling": {"keep": True}, domain: value}}
    row.meta = deepcopy(original)
    db.commit()
    persist_native_report(db, row, None, context=DomainRunContext(None, False), domain=domain)
    assert "meta" not in row.__dict__
    db.commit()
    actual = db.scalar(select(SourceDocument.meta).where(SourceDocument.id == row.id))
    expected = deepcopy(original)
    del expected[KEY][domain]
    assert actual == expected


@pytest.mark.parametrize("container", [False, 0, "invalid", [], [{"nested": True}]])
def test_sqlite_malformed_authority_container_refuses_without_loss(sqlite_source, container):
    db, row = sqlite_source
    original = {"keep": "original", KEY: container}
    row.meta = deepcopy(original)
    db.commit()
    with pytest.raises(ValueError, match="container invalid"):
        persist_native_report(db, row, None, context=DomainRunContext(None, False), domain="national_budget")
    db.rollback()
    assert db.scalar(select(SourceDocument.meta).where(SourceDocument.id == row.id)) == original


def test_sqlite_rollback_and_dry_run_preserve_old_binding(sqlite_source):
    db, row = sqlite_source
    original = {"keep": "original", KEY: {"national_budget": {"extraction_id": 7}}}
    row.meta = deepcopy(original)
    db.commit()
    persist_native_report(db, row, None, context=DomainRunContext(None, False), domain="national_budget")
    db.rollback()
    assert row.meta == original
    persist_native_report(db, row, None, context=DomainRunContext(None, True), domain="national_budget")
    db.commit()
    assert row.meta == original
