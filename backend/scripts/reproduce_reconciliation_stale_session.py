"""Known-defect reproduction for stale OAG reconciliation approval.

From backend/, run: python scripts/reproduce_reconciliation_stale_session.py
Set DATABASE_URL=postgresql://test:test@localhost/unused for import configuration.
This connects only to an auto-removed temporary SQLite database.
The first case demonstrates the defect; the second is a refreshed-state control.
Refreshing alone is not a concurrency fix: validation and writes need serialization.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

# The reviewed checkout's backend cwd, not the dirty primary checkout.
sys.path.insert(0, str(Path.cwd()))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from models import Base, Extraction
from pytest import MonkeyPatch
from tests.test_blue_book_national_walk import national_doc, _legacy_rows, bb
from seeding.extractors.reconciliation import ReconciliationRequired


@compiles(JSONB, "sqlite")
def compile_jsonb(element, compiler, **kw):
    return "TEXT"


def run_probe(refresh):
    with TemporaryDirectory(prefix="oag-review-probe-") as td:
        engine = create_engine("sqlite:///" + td + "/probe.db")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine, autoflush=False)
        a = Session()
        mp = MonkeyPatch()
        try:
            doc = national_doc.__wrapped__(a, Path(td), mp)
            a.add_all(_legacy_rows(doc))
            a.commit()
            candidates = _legacy_rows(doc)
            candidates[0].extracted_json["finding_text"] = "Reviewed correction A"
            try:
                bb.replace_extractions(
                    a, doc, bb.EXTRACTOR_ID, candidates, bb.blue_book_row_key
                )
            except ReconciliationRequired as exc:
                review = {
                    "proposal": exc.proposal,
                    "source_complete": True,
                    "reason": "Exact original source review",
                }
            else:
                raise AssertionError("Changed content must initially require review")
            a.commit()
            # Retain ORM instances in A while B performs and commits a newer edit.
            retained = a.query(Extraction).order_by(Extraction.id).all()
            extraction_id = retained[0].id
            with Session() as b:
                other = b.get(Extraction, extraction_id)
                other.extracted_json = {
                    **other.extracted_json,
                    "finding_text": "NEWER CORRECTION B",
                }
                b.commit()
            with Session() as check:
                assert check.get(Extraction, extraction_id).extracted_json[
                    "finding_text"
                ] == "NEWER CORRECTION B"
            if refresh:
                a.expire_all()
            try:
                bb.replace_extractions(
                    a, doc, bb.EXTRACTOR_ID, candidates,
                    bb.blue_book_row_key, review=review,
                )
                a.commit()
                verdict = "accepted"
            except ReconciliationRequired:
                a.rollback()
                verdict = "refused"
            with Session() as check:
                final = check.get(Extraction, extraction_id).extracted_json[
                    "finding_text"
                ]
            expected = (
                ("refused", "NEWER CORRECTION B")
                if refresh else ("accepted", "Reviewed correction A")
            )
            assert (verdict, final) == expected
            print({
                "explicit_refresh": refresh,
                "stale_review": verdict,
                "stored_text": final,
            })
        finally:
            a.close()
            engine.dispose()
            mp.undo()


for refresh in (False, True):
    run_probe(refresh)
