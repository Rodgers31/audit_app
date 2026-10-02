"""Refuse unidentified debt batches before reconciliation or pending-state flush."""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from decimal import Decimal

import pytest
from models import DebtCategory, DocumentType, Entity, EntityType, Loan, SourceDocument
from seeding.config import SeedingSettings
from seeding.domains import national_debt
from seeding.domains.national_debt import parser, writer
from seeding.types import DomainRunContext
from sqlalchemy import event


def _loan(**changes):
    return {
        "entity_name": "National Government",
        "entity_type": "national",
        "lender": "Incoming creditor",
        "principal": "100",
        "outstanding": "90",
        "issue_date": "2026-01-01",
        "debt_category": "external_multilateral",
        **changes,
    }


@pytest.fixture()
def state(db_session, seed_country):
    entity = Entity(
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="Stored publisher",
        title="Stored edition",
        url="https://example.invalid/stored.pdf",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2025, 1, 1),
    )
    db_session.add_all([entity, doc])
    db_session.flush()
    for lender, category, day in [
        ("Stale external", DebtCategory.EXTERNAL_MULTILATERAL, 1),
        ("Domestic Infrastructure & Green Bonds", DebtCategory.DOMESTIC_BONDS, 1),
        ("Domestic Treasury Bonds", DebtCategory.DOMESTIC_BONDS, 1),
        ("Domestic Treasury Bonds", DebtCategory.DOMESTIC_BONDS, 2),
    ]:
        db_session.add(
            Loan(
                entity_id=entity.id,
                lender=lender,
                debt_category=category,
                principal=Decimal("12"),
                outstanding=Decimal("11"),
                interest_rate=Decimal("0"),
                currency="KES",
                issue_date=datetime(2025, 1, day),
                source_document_id=doc.id,
                provenance=[{"retained": lender}],
            )
        )
    db_session.flush()
    return entity, doc


def _snapshot(session):
    with session.no_autoflush:
        return {
            model.__tablename__: [
                deepcopy(
                    tuple(
                        getattr(row, attribute.key)
                        for attribute in model.__mapper__.column_attrs
                    )
                )
                for row in session.query(model).order_by(model.id).all()
            ]
            for model in (SourceDocument, Loan)
        }


def _mixed_payload():
    return {
        "loans": [
            _loan(
                source_url="https://example.invalid/stored.pdf",
                source_title="Stored edition",
                publisher="Declared new publisher",
            ),
            _loan(
                lender="Domestic Treasury Bonds",
                debt_category="domestic_bonds",
                source_title="Valid domestic edition",
            ),
            _loan(lender="Unidentified later row", source_title=None),
        ]
    }


def test_full_writer_refuses_mixed_batch_before_any_mutator_or_flush(
    db_session, state, monkeypatch
):
    _, doc = state
    before = _snapshot(db_session)
    doc.publisher = "Caller pending publisher"
    pending = SourceDocument(
        country_id=doc.country_id,
        title="Caller pending document",
        publisher="Caller",
        doc_type=DocumentType.LOAN,
        fetch_date=datetime(2026, 1, 1),
    )
    db_session.add(pending)
    dirty, new, deleted = (
        set(db_session.dirty),
        set(db_session.new),
        set(db_session.deleted),
    )
    calls = []
    for name in (
        "reconcile_external_creditors",
        "drop_subsumed_stored_rows",
        "_get_or_create_entity",
        "_get_or_create_source_document",
    ):
        original = getattr(writer, name)

        def spy(*a, _name=name, _original=original, **k):
            calls.append(_name)
            return _original(*a, **k)

        monkeypatch.setattr(writer, name, spy)
    statements = []
    connection = db_session.connection()

    def observe(*a):
        statements.append(True)

    event.listen(connection, "before_cursor_execute", observe)
    try:
        with pytest.raises(ValueError, match=r"source identity.*record #3"):
            writer.write_debt_records(
                db_session, parser.parse_debt_payload(_mixed_payload()), "t", None
            )
        assert not calls and not statements
        assert (
            set(db_session.dirty),
            set(db_session.new),
            set(db_session.deleted),
        ) == (dirty, new, deleted)
        assert pending.id is None
    finally:
        event.remove(connection, "before_cursor_execute", observe)
    after = _snapshot(db_session)
    # Caller-owned pending edits survive; every writer-owned row remains unchanged.
    before["source_documents"][0] = tuple(
        "Caller pending publisher" if c.key == "publisher" else value
        for c, value in zip(
            SourceDocument.__table__.columns, before["source_documents"][0]
        )
    )
    assert after == before


@pytest.mark.parametrize("title", [None, "", "   "])
def test_configured_json_domain_records_refusal_without_partial_write(
    db_session, state, tmp_path, title
):
    payload = _mixed_payload()
    payload["loans"][-1]["source_title"] = title
    path = tmp_path / "configurable-debt.json"
    path.write_text(json.dumps(payload))
    settings = SeedingSettings(
        national_debt_dataset_url=path.as_uri(),
        live_pdf_fetch_enabled=False,
        http_cache_enabled=False,
        storage_path=tmp_path,
        cache_path=tmp_path / "cache",
    )
    before = _snapshot(db_session)
    result = national_debt.run(
        db_session, settings, DomainRunContext(since=None, dry_run=False)
    )
    assert result.items_created == result.items_updated == 0
    assert result.items_processed == 3
    assert any(
        "Write failed:" in e and "source identity" in e and "record #3" in e
        for e in result.errors
    )
    assert _snapshot(db_session) == before
    assert not db_session.new and not db_session.dirty and not db_session.deleted


@pytest.mark.parametrize("title", [None, "", "   ", 42, {}, []])
def test_direct_source_helper_refuses_unidentified_or_malformed_titles(
    db_session, state, title
):
    record = parser.DebtRecord(
        "National Government",
        "national",
        "x",
        Decimal(1),
        Decimal(1),
        datetime(2026, 1, 1),
        None,
        "KES",
        source_title=title,
    )
    before = _snapshot(db_session)
    with pytest.raises(ValueError, match="source identity"):
        writer._get_or_create_source_document(db_session, record)
    assert _snapshot(db_session) == before


@pytest.mark.parametrize(
    "fields",
    [{}, {"source_title": None}, {"source_title": ""}, {"source_title": "   "}],
)
def test_missing_title_never_becomes_declared_identity(db_session, state, fields):
    records = parser.parse_debt_payload({"loans": [_loan()], **fields})
    assert len(records) == 1
    with pytest.raises(ValueError, match="source identity"):
        writer.write_debt_records(db_session, records, "t", None)


@pytest.mark.parametrize(
    "fields",
    [
        {"source_title": "National Treasury Debt Bulletin"},
        {"source_title": "Treasury edition 2026"},
        {
            "source_url": "https://example.invalid/edition 2026.pdf",
            "source_title": None,
        },
        {
            "source_url": "https://example.invalid/edition%202026.pdf",
            "source_title": "",
        },
        {"source_url": "file://test"},
        {"source_url": "/retained/debt.json"},
    ],
)
def test_identified_repeat_batch_keeps_document_and_loan_ids(db_session, state, fields):
    records = parser.parse_debt_payload({"loans": [_loan()], **fields})
    writer.write_debt_records(db_session, records, "t", None)
    db_session.flush()
    before = _snapshot(db_session)
    assert writer.write_debt_records(db_session, records, "t", None) == (0, 0)
    db_session.flush()
    assert _snapshot(db_session) == before


@pytest.mark.parametrize("url", [True, 42, [], {}, "https://example.invalid/\x00x"])
def test_malformed_locator_refuses_even_with_valid_title(db_session, state, url):
    records = parser.parse_debt_payload(
        {"loans": [_loan()], "source_title": "Declared edition", "source_url": url}
    )
    with pytest.raises(ValueError, match="source identity"):
        writer.write_debt_records(db_session, records, "t", None)


def test_valid_mixed_batch_runs_reconciliation_deletion_and_dedupe(db_session, state):
    payload = _mixed_payload()
    payload["loans"].pop()
    writer.write_debt_records(db_session, parser.parse_debt_payload(payload), "t", None)
    db_session.flush()
    assert {row.lender for row in db_session.query(Loan)} == {
        "Incoming creditor",
        "Domestic Treasury Bonds",
    }
    assert state[1].publisher == "Declared new publisher"


@pytest.mark.parametrize("title", [None, "", "   "])
def test_configured_unidentified_payload_never_creates_duplicate_documents(
    db_session, state, tmp_path, title
):
    payload = {"source_title": title, "loans": [_loan()]}
    path = tmp_path / "unidentified.json"
    path.write_text(json.dumps(payload))
    settings = SeedingSettings(
        national_debt_dataset_url=path.as_uri(),
        live_pdf_fetch_enabled=False,
        http_cache_enabled=False,
        storage_path=tmp_path,
        cache_path=tmp_path / "cache",
    )
    before = _snapshot(db_session)
    for _ in range(2):
        result = national_debt.run(
            db_session, settings, DomainRunContext(since=None, dry_run=False)
        )
        assert result.items_created == result.items_updated == 0
        assert any(
            "Write failed:" in e and "source identity" in e for e in result.errors
        )
        assert _snapshot(db_session) == before


@pytest.mark.parametrize("title", [None, "", "   "])
def test_valid_locator_allows_absent_display_title(db_session, state, title):
    payload = {
        "source_url": "https://example.invalid/declared.pdf",
        "source_title": title,
        "loans": [_loan()],
    }
    records = parser.parse_debt_payload(payload)
    writer.write_debt_records(db_session, records, "t", None)
    db_session.flush()
    before = _snapshot(db_session)
    assert writer.write_debt_records(db_session, records, "t", None) == (0, 0)
    db_session.flush()
    assert _snapshot(db_session) == before


@pytest.mark.parametrize("field", ["source_url", "source_title"])
@pytest.mark.parametrize("value", [False, [], {}, 42])
def test_malformed_row_identity_is_not_hidden_by_inheritance(
    db_session, state, field, value
):
    payload = {
        "source_url": "https://example.invalid/payload.pdf",
        "source_title": "Declared payload edition",
        "loans": [_loan(**{field: value})],
    }
    records = parser.parse_debt_payload(payload)
    assert len(records) == 1
    assert getattr(records[0], field) == value
    with pytest.raises(ValueError, match="source identity"):
        writer.write_debt_records(db_session, records, "t", None)


def test_declared_title_and_locator_are_trimmed_once_without_input_mutation(
    db_session, state
):
    records = parser.parse_debt_payload(
        {
            "source_title": "  Declared edition  ",
            "source_url": "  https://example.invalid/space edition.pdf  ",
            "loans": [_loan()],
        }
    )
    writer.write_debt_records(db_session, records, "t", None)
    db_session.flush()
    record = records[0]
    assert record.source_title == "  Declared edition  "
    assert record.source_url == "  https://example.invalid/space edition.pdf  "
    doc = db_session.query(SourceDocument).filter_by(title="Declared edition").one()
    assert doc.url == "https://example.invalid/space edition.pdf"
    assert writer.write_debt_records(db_session, records, "t", None) == (0, 0)


def test_refusal_error_omits_credential_bearing_locator(db_session, state):
    secret = "do-not-display"
    records = parser.parse_debt_payload(
        {
            "source_title": "Declared edition",
            "source_url": f"https://user:{secret}@example.invalid/\x00doc",
            "loans": [_loan()],
        }
    )
    with pytest.raises(
        ValueError, match="source_url contains nonprinting characters"
    ) as error:
        writer.write_debt_records(db_session, records, "t", None)
    assert secret not in str(error.value)


def test_display_fallback_never_merges_unrelated_declared_title(db_session, state):
    first = parser.parse_debt_payload(
        {
            "source_url": "https://example.invalid/world-bank.pdf",
            "publisher": "World Bank",
            "loans": [_loan(lender="World Bank creditor")],
        }
    )
    writer.write_debt_records(db_session, first, "t", None)
    db_session.flush()
    old = db_session.query(SourceDocument).filter_by(url=first[0].source_url).one()
    second = parser.parse_debt_payload(
        {
            "source_title": "National Treasury Debt Bulletin",
            "publisher": "Central Bank of Kenya",
            "loans": [_loan(lender="Independent declared creditor")],
        }
    )
    writer.write_debt_records(db_session, second, "t", None)
    db_session.flush()
    loan = db_session.query(Loan).filter_by(lender=second[0].lender).one()
    assert loan.source_document_id != old.id
    assert old.publisher == "World Bank"
    assert writer.write_debt_records(db_session, second, "t", None) == (0, 0)


def test_same_locator_can_declare_generated_title_without_changing_source_id(
    db_session, state
):
    record = parser.parse_debt_payload(
        {"source_url": "https://example.invalid/edition.pdf", "loans": [_loan()]}
    )[0]
    old = writer._get_or_create_source_document(db_session, record)
    old.meta = {**old.meta, "retained": "other metadata"}
    old_id = old.id
    record.source_title = "Declared edition"
    declared = writer._get_or_create_source_document(db_session, record)
    assert declared.id == old_id and declared.title == "Declared edition"
    assert declared.meta["retained"] == "other metadata"
    record.source_url = None
    assert writer._get_or_create_source_document(db_session, record).id == old_id


def test_legacy_declared_default_title_keeps_existing_id(db_session, state):
    _, doc = state
    doc.title = "National Treasury Debt Bulletin"
    db_session.flush()
    record = parser.parse_debt_payload({"source_title": doc.title, "loans": [_loan()]})[
        0
    ]
    assert writer._get_or_create_source_document(db_session, record).id == doc.id


@pytest.mark.parametrize("field", ["source_url", "source_title"])
@pytest.mark.parametrize("value", ["\ud800", "\u200b", "edition\u0080"])
def test_nonprinting_or_unencodable_identity_is_refused_before_reconciliation(
    db_session, state, field, value
):
    records = parser.parse_debt_payload(
        {
            "source_title": "Declared edition",
            "source_url": "https://example.invalid/debt.pdf",
            "loans": [_loan(**{field: value})],
        }
    )
    before = _snapshot(db_session)
    with pytest.raises(ValueError, match="source identity"):
        writer.write_debt_records(db_session, records, "t", None)
    assert _snapshot(db_session) == before
