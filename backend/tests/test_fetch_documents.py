"""Layer-2 fetcher: AVAILABLE must mean bytes landed; failure fails closed.

The audit found 48 documents marked AVAILABLE with no URL — availability
nobody checked. These tests pin the new contract: a failed download
leaves the row FAILED with the error recorded AND re-raises; a re-issued
document preserves the old md5 for invalidation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from models import DocumentStatus, DocumentType, SourceDocument
from seeding.config import SeedingSettings
from seeding.fetch_documents import fetch_document
from seeding.http_client import PdfDownloadError

URL = "https://www.oagkenya.go.ke/wp-content/uploads/2026/05/REPORT-2024-2025.pdf"


@pytest.fixture()
def settings(tmp_path):
    return SeedingSettings(
        storage_path=tmp_path / "storage", cache_path=tmp_path / "cache"
    )


def _fake_pdf(tmp_path: Path, content: bytes = b"%PDF-1.7 fake body") -> Path:
    p = tmp_path / "fake.pdf"
    p.write_bytes(content)
    return p


class TestFetchDocument:
    def test_success_records_everything_and_marks_available(
        self, db_session, seed_country, settings, tmp_path
    ):
        pdf = _fake_pdf(tmp_path)
        with patch(
            "seeding.fetch_documents.get_or_download_pdf", return_value=pdf
        ):
            doc = fetch_document(
                db_session,
                client=None,
                settings=settings,
                url=URL,
                country_id=seed_country.id,
                publisher="Office of the Auditor-General",
                title="REPORT-2024-2025.pdf",
                doc_type=DocumentType.AUDIT,
                dataset_id="oag_national_audits",
            )
        assert doc.status == DocumentStatus.AVAILABLE
        assert doc.md5 is not None and len(doc.md5) == 32
        assert doc.file_path == str(pdf)
        assert doc.http_status == 200
        assert doc.last_verified_at is not None
        assert doc.meta["dataset_id"] == "oag_national_audits"

    def test_failure_fails_closed(self, db_session, seed_country, settings):
        # POSITIVE CONTROL: the failure path must (a) not mark AVAILABLE,
        # (b) record why, and (c) re-raise — never a quiet success.
        with patch(
            "seeding.fetch_documents.get_or_download_pdf",
            side_effect=PdfDownloadError("timed out after 600s"),
        ):
            with pytest.raises(PdfDownloadError):
                fetch_document(
                    db_session,
                    client=None,
                    settings=settings,
                    url=URL,
                    country_id=seed_country.id,
                    publisher="Office of the Auditor-General",
                    title="REPORT-2024-2025.pdf",
                    doc_type=DocumentType.AUDIT,
                )
        doc = db_session.query(SourceDocument).filter_by(url=URL).one()
        assert doc.status == DocumentStatus.FAILED
        assert "timed out" in doc.meta["fetch_error"]
        assert doc.md5 is None

    def test_reissued_document_preserves_old_md5(
        self, db_session, seed_country, settings, tmp_path
    ):
        first = _fake_pdf(tmp_path, b"%PDF-1.7 original")
        with patch(
            "seeding.fetch_documents.get_or_download_pdf", return_value=first
        ):
            doc = fetch_document(
                db_session,
                client=None,
                settings=settings,
                url=URL,
                country_id=seed_country.id,
                publisher="OAG",
                title="R.pdf",
                doc_type=DocumentType.AUDIT,
            )
        old_md5 = doc.md5

        reissued = tmp_path / "reissued.pdf"
        reissued.write_bytes(b"%PDF-1.7 the publisher changed the file")
        with patch(
            "seeding.fetch_documents.get_or_download_pdf", return_value=reissued
        ):
            doc = fetch_document(
                db_session,
                client=None,
                settings=settings,
                url=URL,
                country_id=seed_country.id,
                publisher="OAG",
                title="R.pdf",
                doc_type=DocumentType.AUDIT,
            )
        assert doc.md5 != old_md5
        assert doc.meta["previous_md5"] == old_md5

    def test_wrong_title_corrected_with_history(
        self, db_session, seed_country, settings, tmp_path
    ):
        # Doc 2392 was filed as "County Audit Findings" while holding the
        # national report; the fetcher owns metadata and corrects it.
        db_session.add(
            SourceDocument(
                country_id=seed_country.id,
                publisher="Office of the Auditor-General",
                title="County Audit Findings",
                url=URL,
                fetch_date=datetime(2026, 7, 19, tzinfo=timezone.utc),
                doc_type=DocumentType.AUDIT,
                status=DocumentStatus.AVAILABLE,
            )
        )
        db_session.commit()
        pdf = _fake_pdf(tmp_path)
        with patch(
            "seeding.fetch_documents.get_or_download_pdf", return_value=pdf
        ):
            doc = fetch_document(
                db_session,
                client=None,
                settings=settings,
                url=URL,
                country_id=seed_country.id,
                publisher="Office of the Auditor-General",
                title="REPORT-2024-2025.pdf",
                doc_type=DocumentType.AUDIT,
            )
        assert doc.title == "REPORT-2024-2025.pdf"
        assert "County Audit Findings" in doc.meta["previous_titles"]
