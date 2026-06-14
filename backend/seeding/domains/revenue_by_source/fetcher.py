"""Fetch revenue-by-source payload with live World Bank enrichment.

Strategy:
1. Try World Bank API for government revenue indicators (total revenue,
   tax revenue as % of GDP) to get authoritative headline figures.
2. Load fixture for the detailed tax-type breakdown (PAYE, VAT, Corp Tax,
   Excise Duty) which is only available from KRA annual reports.
3. Merge: live headline figures enrich the fixture breakdown.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.revenue_by_source.fetcher")

_WB_BASE = "https://api.worldbank.org/v2/country/KEN/indicator"

# World Bank revenue indicators
_WB_REVENUE_INDICATORS = {
    "GC.REV.TOTL.CN": {
        "revenue_type": "Total Government Revenue",
        "description": "Total revenue in current LCU (KES)",
    },
    "GC.TAX.TOTL.CN": {
        "revenue_type": "Total Tax Revenue",
        "description": "Total tax revenue in current LCU (KES)",
    },
    "GC.TAX.TOTL.GD.ZS": {
        "revenue_type": "Tax Revenue % of GDP",
        "description": "Tax revenue as share of GDP",
    },
}


def _fetch_wb_revenue(
    client: SeedingHttpClient, settings: SeedingSettings
) -> List[Dict[str, Any]]:
    """Fetch revenue data from World Bank API.

    Returns list of revenue records compatible with the fixture format.
    """
    records: List[Dict[str, Any]] = []

    for indicator_code, meta in _WB_REVENUE_INDICATORS.items():
        try:
            url = f"{_WB_BASE}/{indicator_code}"
            logger.info("Fetching World Bank %s ...", indicator_code)

            resp = client.get(
                url,
                params={"format": "json", "per_page": "20", "date": "2018:2026"},
                raise_for_status=True,
            )
            wb_data = resp.json()

            if not isinstance(wb_data, list) or len(wb_data) < 2 or not wb_data[1]:
                continue

            for item in wb_data[1]:
                if item.get("value") is None:
                    continue

                year = int(item["date"])
                value = item["value"]

                # Convert LCU to billions KES for monetary values
                if indicator_code.endswith(".CN"):
                    amount_billions = round(value / 1e9, 1)
                    records.append({
                        "fiscal_year": f"FY {year - 1}/{str(year)[-2:]}",
                        "revenue_type": meta["revenue_type"],
                        "amount_billion_kes": amount_billions,
                        "target_billion_kes": None,
                        "performance_pct": None,
                        "share_of_total_pct": None,
                        "yoy_growth_pct": None,
                        "source": f"World Bank ({indicator_code})",
                        "source_url": (
                            f"https://data.worldbank.org/indicator/"
                            f"{indicator_code}?locations=KE"
                        ),
                        "data_quality": "official",
                    })

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank %s: %s", indicator_code, exc
            )

    return records


def fetch_revenue_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> list[dict[str, Any]]:
    """Fetch revenue data, trying live sources first.

    Strategy:
    1. Fetch headline revenue from World Bank API.
    2. Load fixture for detailed tax-type breakdown.
    3. Merge: live headline data supplements fixture detail.
    """
    live_records: List[Dict[str, Any]] = []

    # Step 1: Try World Bank API
    if settings.enrich_with_worldbank:
        try:
            live_records = _fetch_wb_revenue(client, settings)
            if live_records:
                logger.info(
                    "Fetched %d revenue records from World Bank", len(live_records)
                )
        except Exception as exc:
            logger.warning("World Bank revenue fetch failed: %s", exc)

    # Step 2: Load fixture
    try:
        fixture_payload = load_json_resource(
            url=settings.revenue_by_source_dataset_url,
            client=client,
            logger=logger,
            label="revenue_by_source",
        )
        if not isinstance(fixture_payload, list):
            fixture_payload = []
    except Exception as exc:
        logger.warning("Failed to load revenue fixture: %s", exc)
        fixture_payload = []

    # Step 3: Merge — fixture provides detail, live provides headline totals
    if live_records:
        # Index fixture by (fiscal_year, revenue_type)
        fixture_keys = {
            (r.get("fiscal_year", ""), r.get("revenue_type", ""))
            for r in fixture_payload
        }

        # Add live records that don't overlap with fixture detail
        merged = list(fixture_payload)
        for record in live_records:
            key = (record.get("fiscal_year", ""), record.get("revenue_type", ""))
            if key not in fixture_keys:
                merged.append(record)

        logger.info(
            "Merged revenue: %d fixture + %d new live = %d total",
            len(fixture_payload),
            len(merged) - len(fixture_payload),
            len(merged),
        )
        final_payload = merged
    elif fixture_payload:
        logger.warning(
            "No live revenue data — using fixture as fallback (data may be stale)"
        )
        final_payload = fixture_payload
    else:
        raise ValueError(
            "No revenue data available from either live API or fixture"
        )

    # Step 4: live KRA per-tax-head overlay (opt-in via settings.kra_revenue_url).
    # Refreshes the PAYE/VAT/Corporation/Excise/Customs breakdown from KRA's FY
    # revenue results — but only if the parse passes the plausibility +
    # reconciliation gate; otherwise the fixture breakdown stands.
    if settings.kra_revenue_url:
        try:
            final_payload, status = _apply_kra_overlay(
                final_payload, client, settings
            )
            logger.info("revenue_by_source KRA overlay: %s", status)
        except Exception as exc:
            logger.warning("KRA revenue overlay skipped: %s", exc)

    return final_payload


def _fetch_kra_text(client: SeedingHttpClient, url: str) -> str:
    """Fetch the KRA revenue source (PDF or HTML) and return plain text."""
    resp = client.get(url, raise_for_status=True)
    ctype = (resp.headers.get("content-type") or "").lower()
    if "pdf" in ctype or url.lower().endswith(".pdf"):
        import tempfile
        from pathlib import Path

        import pdfplumber

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf", delete=False, prefix="kra_rev_"
            ) as tmp:
                tmp.write(resp.content)
                tmp_path = Path(tmp.name)
            parts: List[str] = []
            with pdfplumber.open(tmp_path) as pdf:
                for page in pdf.pages[:8]:
                    parts.append(page.extract_text() or "")
            return "\n".join(parts)
        finally:
            if tmp_path and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
    # HTML — strip tags to plain text so the money/anchor regexes see the prose.
    import re as _re

    return _re.sub(r"<[^>]+>", " ", resp.text)


def _apply_kra_overlay(
    payload: List[Dict[str, Any]],
    client: SeedingHttpClient,
    settings: SeedingSettings,
) -> tuple[List[Dict[str, Any]], str]:
    """Fetch KRA results, extract the per-head breakdown, and overlay it onto the
    matched fiscal year's tax rows — only if it passes the validation gate.
    Returns ``(payload, status)``. Safe-by-construction: any failure / empty /
    non-reconciling parse leaves the payload unchanged.
    """
    from .kra_parser import (
        extract_kra_fiscal_year,
        extract_kra_revenue_by_type_from_text,
    )

    text = _fetch_kra_text(client, settings.kra_revenue_url)
    by_type = {k: float(v) for k, v in extract_kra_revenue_by_type_from_text(text).items()}
    fy = extract_kra_fiscal_year(text)
    return _overlay_kra_breakdown(payload, by_type, fy)


def _overlay_kra_breakdown(
    payload: List[Dict[str, Any]],
    by_type: Dict[str, float],
    fiscal_year: Optional[str],
) -> tuple[List[Dict[str, Any]], str]:
    """Validate ``by_type`` and overlay it onto the tax rows of ``fiscal_year``
    (or the latest fixture FY if none parsed). Pure; no network. Returns
    ``(payload, status)``."""
    if not by_type:
        return payload, "no_live_value"

    tax_rows = [
        r
        for r in payload
        if str(r.get("category", "tax")).lower() == "tax" and r.get("fiscal_year")
    ]
    if not tax_rows:
        return payload, "no_fixture"

    target_fy = fiscal_year
    if target_fy not in {r["fiscal_year"] for r in tax_rows}:
        target_fy = max(r["fiscal_year"] for r in tax_rows)  # fall back to latest
    fy_rows = [r for r in tax_rows if r["fiscal_year"] == target_fy]

    def _amt(r: Dict[str, Any]) -> float:
        v = r.get("amount_billion_kes")
        if v is None:
            v = r.get("target_billion_kes")
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    expected_total = sum(_amt(r) for r in fy_rows) or None

    from services.trust_guards import check_revenue_breakdown

    if check_revenue_breakdown(by_type, expected_total):
        return payload, "failed_validation"

    by_name = {r.get("revenue_type"): r for r in fy_rows}
    applied = 0
    for rtype, amount in by_type.items():
        rec = by_name.get(rtype)
        if rec is not None:
            rec["amount_billion_kes"] = round(amount, 1)
            rec["data_quality"] = "official"
            rec["_revenue_source"] = "kra_live"
            applied += 1

    return payload, (f"promoted:{applied}/{target_fy}" if applied else "no_match")
