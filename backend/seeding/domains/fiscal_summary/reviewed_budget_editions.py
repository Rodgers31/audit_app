"""Verify reviewed legacy Treasury editions without replacing published fiscal values."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from services.response_receipts import acquisition_is_intact

from .fiscal_framework import AnnexTable, FiscalFrameworkError, REQUIRED_ROWS, gate_column

MANIFEST = Path(__file__).with_name("data") / "reviewed_budget_editions.json"
VERIFIED_PRINTED_EDITION = "verified_printed_edition"


def load_reviewed_budget_editions():
    return json.loads(MANIFEST.read_bytes())


def verify_reviewed_budget_edition(client, settings, profile):
    """Require a fresh full response for the exact source reviewed in the manifest."""
    url = profile["pdf_url"]
    digest = profile["sha256"]
    size = profile["size_bytes"]
    page = profile["annex_page"]
    values = profile["budget_column_kes_billions"]
    if set(values) != set(REQUIRED_ROWS):
        raise FiscalFrameworkError("reviewed_annex_inventory_refused")
    table = AnnexTable({key: [Decimal(value)] for key, value in values.items()}, width=1, page=page)
    gate_column(table, 0, fiscal_year=profile["fiscal_year"], identified_by="printed_budget_column")

    with TemporaryDirectory(prefix="reviewed-budget-edition-") as scratch:
        target = Path(scratch) / "edition.pdf"
        client.download_to_file(
            url,
            target,
            max_seconds=min(settings.pdf_download_timeout_seconds, 60),
            max_bytes=min(settings.pdf_download_max_bytes, size),
        )
        with target.open("rb") as stream:
            measured = hashlib.file_digest(stream, "sha256").hexdigest()
        receipt = client.download_receipt(url)
        if (
            target.stat().st_size != size
            or measured != digest
            or not acquisition_is_intact(receipt)
            or receipt.get("digest") != digest
            or receipt.get("request_url") != url
            or receipt.get("response_url") != url
            or receipt.get("status") != 200
            or receipt.get("byte_check", {}).get("status") != "matched"
        ):
            raise FiscalFrameworkError("reviewed_budget_edition_identity_refused")
    return {
        "status": VERIFIED_PRINTED_EDITION,
        "fiscal_year": profile["fiscal_year"],
        "pdf_url": url,
        "sha256": digest,
        "annex_page": page,
        "column": profile["column"],
    }
