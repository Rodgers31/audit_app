"""Fetcher for pending bills data from National Treasury BROP.

Strategy (in order):
1. If live_pdf_fetch_enabled AND treasury_brop_url is configured,
   download and parse the BROP PDF — gives the para-18 national
   aggregate + Table 10 per-county breakdown.
2. If pending_bills_dataset_url is configured, load from that
   fixture / API.
3. Otherwise, run the live ETL extractor against COB website.

Why not the COB NG-BIRR
-----------------------
The previous implementation downloaded the COB National Government
BIRR and ran it through ``CoBQuarterlyReportParser``, which is
anchored on the 47-county invariant of the *Consolidated County*
BIRR. The NG-BIRR has neither a 47-county table nor any pending-
bills tables (TOC search confirmed in the FY 2025/26 H1 issue).
On top of that, the fallback formula ``pending = allocated -
absorbed`` was a non-sequitur — that's unspent budget, not unpaid
obligations. Both issues are removed here.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient

logger = logging.getLogger("seeding.pending_bills.fetcher")


def fetch_pending_bills_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """
    Fetch pending bills data.

    Strategy:
      1. Try live BROP fetch (if enabled + URL configured).
      2. If pending_bills_dataset_url is configured, load fixture/API.
      3. Otherwise, run the live ETL extractor against COB website.
    """
    # Strategy 1: Treasury BROP. ``treasury_brop_url`` ships with the
    # latest known BROP URL as its default and is overridable via
    # ``SEED_TREASURY_BROP_URL`` env var when the next BROP drops; an
    # operator can also explicitly set it to None to fall through to
    # the fixture path (Strategy 2). The ``getattr`` fallback to
    # ``None`` is defensive — older settings instances may not have
    # the field if a stale module is imported.
    brop_url = getattr(settings, "treasury_brop_url", None)
    if settings.live_pdf_fetch_enabled and brop_url:
        try:
            payload = _fetch_from_treasury_brop(client, brop_url)
            if payload and (
                payload.get("pending_bills") or payload.get("summary")
            ):
                logger.info(
                    "Successfully fetched pending bills from BROP "
                    "(%d records)",
                    len(payload.get("pending_bills") or []),
                )
                return payload
            logger.warning(
                "BROP fetch returned no pending bills, trying fixture"
            )
        except Exception as exc:
            logger.warning(
                "BROP fetch failed, trying fixture: %s", exc
            )
    elif settings.live_pdf_fetch_enabled:
        logger.info(
            "treasury_brop_url not configured; skipping live BROP fetch"
        )

    # Strategy 2: Configured fixture / API URL
    dataset_url = getattr(settings, "pending_bills_dataset_url", None)
    if dataset_url:
        logger.info("Fetching pending bills from configured URL: %s", dataset_url)
        from ...utils import load_json_resource

        return load_json_resource(
            url=dataset_url,
            client=client,
            logger=logger,
            label="pending_bills",
        )

    # Strategy 3: Live ETL extraction
    logger.info(
        "No pending_bills_dataset_url configured. Running live COB extraction..."
    )
    return _run_live_extraction()


def _fetch_from_treasury_brop(
    client: SeedingHttpClient, brop_url: str,
) -> Optional[Dict[str, Any]]:
    """Download the BROP PDF, parse it, return pending bills payload.

    file:// URLs are read from disk so tests and offline runs don't
    require a live HTTP path.
    """
    from .brop_parser import parse_brop_pdf

    logger.info("Downloading Treasury BROP PDF: %s", brop_url)
    tmp_path: Optional[Path] = None
    try:
        if brop_url.startswith("file://"):
            content = Path(brop_url[len("file://"):]).read_bytes()
        else:
            response = client.get(brop_url, raise_for_status=True)
            content = response.content

        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="treasury_brop_"
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.info("Downloaded BROP PDF (%d bytes) to %s", len(content), tmp_path)
        result = parse_brop_pdf(tmp_path)

        return _brop_result_to_payload(result, brop_url)
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _brop_result_to_payload(
    result, brop_url: str,
) -> Dict[str, Any]:
    """Convert a ``BropParseResult`` into the dict shape
    ``parse_pending_bills_payload`` expects.

    Emits:
    * One ``state_corporation`` record for the SOEs aggregate.
    * One ``mda`` record for the MDAs aggregate.
    * One ``county`` record per parsed county row.
    * A ``summary`` block with grand totals so the parser's
      summary-fallback path can also produce useful aggregates if
      the per-row records get filtered out downstream.
    """
    pending_bills: List[Dict[str, Any]] = []
    fy_label = result.fiscal_year_label
    source_title = f"Treasury BROP {fy_label}"

    if result.national:
        nb = result.national
        as_at = nb.as_at_date.isoformat()
        pending_bills.append(
            {
                "entity_name": "National Government — State Corporations",
                "entity_type": "national",
                "category": "state_corporation",
                "fiscal_year": fy_label,
                "total_pending": str(nb.state_corporations),
                "notes": f"Treasury BROP para-18 aggregate as at {as_at}",
            }
        )
        pending_bills.append(
            {
                "entity_name": "National Government — MDAs",
                "entity_type": "national",
                "category": "mda",
                "fiscal_year": fy_label,
                "total_pending": str(nb.mdas),
                "notes": f"Treasury BROP para-18 aggregate as at {as_at}",
            }
        )

    for cb in result.counties:
        breakdown_parts = []
        if cb.executive_subtotal is not None:
            breakdown_parts.append(
                f"Exec subtotal {float(cb.executive_subtotal):,.0f}"
            )
        if cb.assembly_subtotal is not None:
            breakdown_parts.append(
                f"Assembly subtotal {float(cb.assembly_subtotal):,.0f}"
            )
        if cb.fy_budget is not None:
            breakdown_parts.append(
                f"FY budget {float(cb.fy_budget):,.0f}"
            )
        notes = "Treasury BROP Table 10"
        if breakdown_parts:
            notes += " — " + "; ".join(breakdown_parts)
        # Match the fixture's "{County} County" entity-name format —
        # the writer's _get_or_create_entity does an exact
        # canonical_name match first, and that's the format the
        # bootstrap-seeded county entities use. Earlier seed run
        # 24966698677 had this code emitting "County Government of
        # X" which fell through to the ILIKE fallback and failed for
        # all 46 counties.
        pending_bills.append(
            {
                "entity_name": f"{cb.county} County",
                "entity_type": "county",
                "category": "county",
                "fiscal_year": fy_label,
                "total_pending": str(cb.total),
                "notes": notes,
            }
        )

    # Summary aggregates — useful for headline cards and as a
    # fallback if per-row writers drop records.
    summary: Dict[str, Any] = {"fiscal_year": fy_label}
    if result.national:
        summary["total_national"] = str(result.national.total)
        summary["as_at_date"] = result.national.as_at_date.isoformat()
    if result.counties:
        summary["total_county"] = str(
            sum((c.total for c in result.counties), Decimal(0))
        )

    return {
        "pending_bills": pending_bills,
        "summary": summary,
        "source_url": brop_url,
        "source_title": source_title,
    }


def _run_live_extraction() -> dict[str, Any]:
    """Run the pending bills ETL extractor against the COB website."""
    try:
        from etl.pending_bills_extractor import PendingBillsExtractor

        extractor = PendingBillsExtractor()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(extractor.extract_all())
        finally:
            loop.close()

        if not result.get("pending_bills") and not result.get("summary", {}).get(
            "grand_total"
        ):
            logger.warning(
                "Live extraction returned no pending bills data. "
                "The COB reports may require Playwright for PDF download. "
                "Consider setting PLAYWRIGHT_ENABLED=1 and "
                "SEED_PENDING_BILLS_DATASET_URL to a fixture file."
            )
        return result

    except ImportError as exc:
        logger.error(
            "Cannot run live extraction: %s. "
            "Install required packages: pip install pdfplumber httpx beautifulsoup4",
            exc,
        )
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }
    except Exception as exc:
        logger.exception("Live extraction failed: %s", exc)
        return {
            "pending_bills": [],
            "summary": {},
            "source_url": "https://cob.go.ke/publications/",
            "source_title": "Controller of Budget Reports",
            "extraction_error": str(exc),
        }
