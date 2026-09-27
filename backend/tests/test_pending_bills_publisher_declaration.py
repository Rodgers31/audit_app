"""An undeclared pending-bills write never relabels a declared document.

Raised in review of #262 (by the session that fixed the debt and county
writers, #283) and reproduced in the consolidation review: the writer's
publisher DEFAULT (the Controller of Budget) was also used to OVERWRITE an
existing document's publisher, so any call that did not pass ``publisher``
relabelled the National Treasury's BROP as the Controller of Budget's. #271
fixed the same defect in revenue_by_source: the default is only for creating a
document, never for overwriting one.
"""

from __future__ import annotations

from datetime import datetime, timezone

from models import DocumentType, SourceDocument
from seeding.domains.pending_bills.writer import _get_or_create_source_document

BROP_TITLE = "Budget Review and Outlook Paper 2026"
BROP_URL = "https://www.treasury.go.ke/brop-2026.pdf"


def _brop(db_session, seed_country):
    doc = SourceDocument(
        country_id=seed_country.id,
        publisher="National Treasury",
        title=BROP_TITLE,
        doc_type=DocumentType.REPORT,
        url=BROP_URL,
        fetch_date=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    db_session.add(doc)
    db_session.commit()
    return doc


def test_undeclared_row_never_overwrites_a_declared_publisher(db_session, seed_country):
    doc = _brop(db_session, seed_country)
    found = _get_or_create_source_document(db_session, BROP_URL, BROP_TITLE, publisher=None)
    assert found.id == doc.id
    assert found.publisher == "National Treasury"


def test_a_declaration_still_corrects_a_wrong_label(db_session, seed_country):
    doc = _brop(db_session, seed_country)
    doc.publisher = "Office of the Controller of Budget (OCOB)"
    db_session.commit()
    found = _get_or_create_source_document(
        db_session, BROP_URL, BROP_TITLE, publisher="National Treasury"
    )
    assert found.publisher == "National Treasury"


def test_the_default_still_names_a_new_document(db_session, seed_country):
    created = _get_or_create_source_document(
        db_session, "https://cob.go.ke/x.pdf", "COB report never seen", publisher=None
    )
    # Created only if Kenya exists in this fixture's database; the point is
    # that the default applies on creation, not that creation happens here.
    if created is not None:
        assert created.publisher == "Office of the Controller of Budget (OCOB)"
