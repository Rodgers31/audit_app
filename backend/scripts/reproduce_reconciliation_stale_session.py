"""Verify stale OAG reconciliation approval cannot overwrite a newer edit.

Run with ``python backend/scripts/reproduce_reconciliation_stale_session.py``.
Only an auto-removed temporary SQLite database is used. No configured database,
publisher, email service, pytest fixture, or parser monkeypatch is used.

The synthetic source bytes are hashed by the real reconciliation code; this
probe exercises replacement of Extraction rows, not PDF parsing. Two separate
SQLAlchemy sessions reproduce the stale identity-map failure. SQLite verifies
that failure path only; PostgreSQL serialization needs its separate checks.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from models import Base, Country, DocumentType, Extraction, SourceDocument
from seeding.extractors import oag_blue_book as bb
from seeding.extractors.reconciliation import ReconciliationRequired


@compiles(JSONB, "sqlite")
def compile_jsonb(element, compiler, **kw):
    """Use the real models with SQLite's JSON-compatible text storage."""
    return "TEXT"


def _document(session, directory):
    country = Country(
        name="Synthetic probe country", iso_code="TST", currency="KES",
        timezone="UTC", default_locale="en",
    )
    session.add(country)
    session.flush()
    source = directory / "synthetic-source.bin"
    source_bytes = b"Synthetic source bytes for reconciliation-only verification."
    source.write_bytes(source_bytes)
    document = SourceDocument(
        country_id=country.id,
        publisher="Synthetic probe publisher",
        title="Synthetic reconciliation source; not government evidence",
        url="https://example.invalid/synthetic-source.bin",
        file_path=str(source),
        md5=hashlib.md5(source_bytes).hexdigest(),
        fetch_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.AUDIT,
        meta={"probe": "synthetic_reconciliation_only"},
    )
    session.add(document)
    session.flush()
    return document


def _candidate(document, text):
    return Extraction(
        source_document_id=document.id,
        page_number=1,
        extractor=bb.EXTRACTOR_ID,
        confidence=0.90,
        extracted_json={
            "schema": "oag_blue_book/v1",
            "vote": 1001,
            "entity_name": "Synthetic probe institution",
            "fiscal_year": "2024/2025",
            "paragraph_no": 1,
            "title": "Synthetic finding",
            "finding_text": text,
            "pdf_page": 1,
            "printed_page": 1,
            "amounts": [],
        },
    )


def run_probe(refresh):
    with TemporaryDirectory(prefix="oag-review-probe-") as directory:
        directory = Path(directory)
        engine = create_engine("sqlite:///" + str(directory / "probe.db"))

        @event.listens_for(engine, "connect")
        def enable_foreign_keys(connection, _record):
            connection.execute("PRAGMA foreign_keys=ON")

        try:
            Base.metadata.create_all(engine)
            Session = sessionmaker(bind=engine, autoflush=False)
            with Session() as session_a:
                document = _document(session_a, directory)
                session_a.add(_candidate(document, "Original evidence"))
                session_a.commit()
                candidate = _candidate(document, "Reviewed correction A")
                try:
                    bb.replace_extractions(
                        session_a, document, bb.EXTRACTOR_ID, [candidate],
                        bb.blue_book_row_key,
                    )
                except ReconciliationRequired as exc:
                    review = {
                        "proposal": exc.proposal,
                        "source_complete": True,
                        "reason": "Synthetic exact-state source review",
                    }
                else:
                    raise RuntimeError("Changed content did not require initial review")
                session_a.commit()

                # Hold the ORM object strongly so session A's identity map stays
                # stale while an independent session commits a newer correction.
                retained = session_a.query(Extraction).one()
                extraction_id = retained.id
                with Session() as session_b:
                    newer = session_b.get(Extraction, extraction_id)
                    newer.extracted_json = {
                        **newer.extracted_json,
                        "finding_text": "NEWER CORRECTION B",
                    }
                    session_b.commit()
                with Session() as verify:
                    stored = verify.get(Extraction, extraction_id).extracted_json
                    if stored["finding_text"] != "NEWER CORRECTION B":
                        raise RuntimeError("Probe setup did not commit newer evidence")
                if refresh:
                    session_a.expire_all()
                try:
                    bb.replace_extractions(
                        session_a, document, bb.EXTRACTOR_ID, [candidate],
                        bb.blue_book_row_key, review=review,
                    )
                    session_a.commit()
                    verdict = "accepted"
                except ReconciliationRequired:
                    session_a.rollback()
                    verdict = "refused"
                with Session() as verify:
                    final = verify.get(Extraction, extraction_id).extracted_json[
                        "finding_text"
                    ]
                return {
                    "explicit_refresh": refresh,
                    "stale_review": verdict,
                    "stored_text": final,
                }
        finally:
            engine.dispose()


def main():
    results = [run_probe(refresh) for refresh in (False, True)]
    for result in results:
        print(json.dumps(result, sort_keys=True))
    if any(
        row["stale_review"] != "refused"
        or row["stored_text"] != "NEWER CORRECTION B"
        for row in results
    ):
        raise RuntimeError("Stale approval overwrote or failed to preserve newer evidence")
    print("PASS: both stale reviews refused; newer evidence preserved")


if __name__ == "__main__":
    main()
