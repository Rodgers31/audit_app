"""Fetcher for fiscal summary data.

Strategy (in order):
1. Try World Bank Indicators API for government expenditure, external debt,
   and debt service data — merge into the existing fixture payload.
2. Fall back to the static fixture / configured URL.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...config import SeedingSettings
from ...http_client import SeedingHttpClient
from ...utils import load_json_resource

logger = logging.getLogger("seeding.fiscal_summary.fetcher")

# World Bank indicator codes for Kenya
_WB_INDICATORS: Dict[str, str] = {
    "GC.XPN.TOTL.CN": "government_expenditure_lcu",
    "DT.DOD.DECT.CD": "external_debt_stocks_usd",
    "DT.TDS.DECT.CD": "total_debt_service_usd",
    "GC.REV.TOTL.CN": "government_revenue_lcu",
}


def fetch_fiscal_summary_payload(
    client: SeedingHttpClient, settings: SeedingSettings
) -> dict[str, Any]:
    """Fetch fiscal summary data, enriching fixture with World Bank API data."""
    # Always load the fixture as baseline
    payload = load_json_resource(
        url=settings.fiscal_summary_dataset_url,
        client=client,
        logger=logger,
        label="fiscal_summary",
    )

    # Try World Bank enrichment
    if settings.enrich_with_worldbank and settings.live_pdf_fetch_enabled:
        try:
            wb_data = _fetch_worldbank_fiscal_data(client, settings)
            if wb_data:
                payload = _merge_worldbank_data(payload, wb_data)
                logger.info(
                    "Enriched fiscal summary with World Bank data",
                    extra={"wb_years": list(wb_data.keys())},
                )
        except Exception as exc:
            logger.warning(
                "World Bank enrichment failed, using fixture only: %s", exc
            )

    # Live COB NG-BIRR headline overlay (recommendation #3): refine the
    # latest-year appropriated_budget from the authoritative Controller-of-
    # Budget report — but only through the plausibility + reconciliation
    # overlay, so the fixture remains the last-known-good fallback whenever the
    # parse is missing, implausible, or far from the known value.
    if settings.live_pdf_fetch_enabled:
        try:
            live_budget, live_revenue = _fetch_cob_headlines(client, settings)
            payload, b_status = _overlay_live_budget_headline(payload, live_budget)
            payload, r_status = _overlay_live_revenue_headline(payload, live_revenue)
            logger.info(
                "fiscal_summary COB overlay: budget=%s revenue=%s",
                b_status,
                r_status,
            )
        except Exception as exc:
            logger.warning("COB headline overlay skipped: %s", exc)

    return payload


def _fetch_cob_headlines(
    client: SeedingHttpClient, settings: SeedingSettings
) -> tuple[Optional[float], Optional[float]]:
    """Discover + download the latest COB NG-BIRR ONCE and extract the headline
    ``(overall_budget, total_revenue)`` in KSh billion. Returns ``(None, None)``
    on any failure — callers treat that as 'no live value' and keep the
    fixture."""
    import tempfile
    from pathlib import Path

    from ...cob_discovery import discover_latest_cob_pdf_url
    from ..national_budget.fetcher import _NG_BIRR_KEYWORDS
    from ..national_budget.headline import extract_cob_headlines

    resp = client.get(settings.cob_birr_page_url, raise_for_status=True)
    pdf_url = discover_latest_cob_pdf_url(
        resp.text, settings.cob_birr_page_url, keywords=_NG_BIRR_KEYWORDS
    )
    if not pdf_url:
        logger.info("No NG-BIRR PDF found for fiscal_summary headline overlay")
        return None, None

    pdf_resp = client.get(pdf_url, raise_for_status=True)
    tmp_path: Optional["Path"] = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", delete=False, prefix="cob_fs_headline_"
        ) as tmp:
            tmp.write(pdf_resp.content)
            tmp_path = Path(tmp.name)
        budget, revenue = extract_cob_headlines(tmp_path)
        return (
            float(budget) if budget is not None else None,
            float(revenue) if revenue is not None else None,
        )
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def _overlay_live_budget_headline(
    payload: Dict[str, Any],
    live_budget_billion: Optional[float],
    *,
    tolerance_pct: float = 15.0,
) -> tuple[Dict[str, Any], str]:
    """Promote a live-parsed headline budget onto the latest fiscal year ONLY
    if it (a) passes the plausibility gate and (b) reconciles within
    ``tolerance_pct`` of the fixture's last-known value. Otherwise the fixture
    stands. Returns ``(payload, status)`` for logging/tests.

    Safe-by-construction: a missing / implausible / far-off live value is a
    no-op, so a bad COB parse can never replace good data. ``borrowing_pct_of_
    budget`` is left to the parser, which derives it from the (possibly
    overlaid) budget so the share stays consistent.
    """
    if live_budget_billion is None:
        return payload, "no_live_value"
    fiscal_years = payload.get("fiscal_years") or []
    if not fiscal_years:
        return payload, "no_fixture"
    latest = max(fiscal_years, key=lambda r: str(r.get("fiscal_year", "")))
    try:
        live = float(live_budget_billion)
    except (TypeError, ValueError):
        return payload, "bad_live_value"
    if live <= 0:
        return payload, "bad_live_value"

    # (a) plausibility gate — substitute the live budget; it must stay
    # internally consistent (in band; spending still ≤ budget).
    try:
        from services.trust_guards import check_fiscal_summary

        if check_fiscal_summary({**latest, "appropriated_budget": live}):
            return payload, "failed_plausibility"
    except Exception:
        pass  # if the guard can't run, fall through to the tolerance check

    # (b) reconciliation — must be near the last-known fixture value.
    fixture_budget = latest.get("appropriated_budget")
    if fixture_budget:
        try:
            fb = float(fixture_budget)
            if fb > 0 and abs(live - fb) > (tolerance_pct / 100.0) * fb:
                return payload, "outside_tolerance"
        except (TypeError, ValueError):
            pass

    latest["appropriated_budget"] = round(live, 1)
    latest["_budget_source"] = "cob_ng_birr_live"
    return payload, "promoted"


def _overlay_live_revenue_headline(
    payload: Dict[str, Any],
    live_revenue_billion: Optional[float],
    *,
    tolerance_pct: float = 15.0,
) -> tuple[Dict[str, Any], str]:
    """Promote a live-parsed TOTAL revenue onto the latest fiscal year ONLY if
    it (a) passes the plausibility gate and (b) reconciles within
    ``tolerance_pct`` of the fixture's last-known value. ``tax_revenue`` and
    ``non_tax_revenue`` are scaled proportionally so the components keep summing
    to the total (otherwise the #1 reconciliation check would reject the row).
    Otherwise the fixture stands. Safe-by-construction: missing / implausible /
    far-off → no-op.
    """
    if live_revenue_billion is None:
        return payload, "no_live_value"
    fiscal_years = payload.get("fiscal_years") or []
    if not fiscal_years:
        return payload, "no_fixture"
    latest = max(fiscal_years, key=lambda r: str(r.get("fiscal_year", "")))
    try:
        live = float(live_revenue_billion)
    except (TypeError, ValueError):
        return payload, "bad_live_value"
    if live <= 0:
        return payload, "bad_live_value"

    fixture_total = latest.get("total_revenue")
    # Scale the tax/non-tax split proportionally to the new total so components
    # stay consistent (and the plausibility gate's reconciliation check passes).
    candidate = dict(latest)
    candidate["total_revenue"] = live
    if fixture_total:
        try:
            ratio = live / float(fixture_total)
            if latest.get("tax_revenue") is not None:
                candidate["tax_revenue"] = round(float(latest["tax_revenue"]) * ratio, 1)
            if latest.get("non_tax_revenue") is not None:
                candidate["non_tax_revenue"] = round(
                    float(latest["non_tax_revenue"]) * ratio, 1
                )
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    # (a) plausibility gate on the scaled candidate.
    try:
        from services.trust_guards import check_fiscal_summary

        if check_fiscal_summary(candidate):
            return payload, "failed_plausibility"
    except Exception:
        pass

    # (b) reconciliation — must be near the last-known fixture total.
    if fixture_total:
        try:
            ft = float(fixture_total)
            if ft > 0 and abs(live - ft) > (tolerance_pct / 100.0) * ft:
                return payload, "outside_tolerance"
        except (TypeError, ValueError):
            pass

    latest["total_revenue"] = round(live, 1)
    if "tax_revenue" in candidate:
        latest["tax_revenue"] = candidate["tax_revenue"]
    if "non_tax_revenue" in candidate:
        latest["non_tax_revenue"] = candidate["non_tax_revenue"]
    latest["_revenue_source"] = "cob_ng_birr_live"
    return payload, "promoted"


def _fetch_worldbank_fiscal_data(
    client: SeedingHttpClient, settings: SeedingSettings
) -> Dict[str, Dict[str, float]]:
    """Fetch Kenya fiscal indicators from World Bank API.

    Returns:
        Dict keyed by calendar year (str), each containing indicator values.
        E.g. {"2023": {"government_expenditure_lcu": 3200000000000, ...}}
    """
    base_url = settings.worldbank_api_base_url
    result: Dict[str, Dict[str, float]] = {}

    for indicator_code, field_name in _WB_INDICATORS.items():
        try:
            url = f"{base_url}/country/KEN/indicator/{indicator_code}"
            logger.info("Fetching World Bank indicator %s ...", indicator_code)

            response = client.get(
                url,
                params={
                    "format": "json",
                    "per_page": "20",
                    "date": "2018:2025",
                },
                raise_for_status=False,
            )

            if response.status_code != 200:
                logger.warning(
                    "World Bank API returned %d for %s",
                    response.status_code,
                    indicator_code,
                )
                continue

            data = response.json()
            # World Bank API returns [metadata, records]
            if not isinstance(data, list) or len(data) < 2:
                continue

            records = data[1]
            if not records:
                continue

            for record in records:
                year = record.get("date")
                value = record.get("value")
                if year and value is not None:
                    result.setdefault(str(year), {})[field_name] = float(value)

        except Exception as exc:
            logger.warning(
                "Failed to fetch World Bank indicator %s: %s",
                indicator_code,
                exc,
            )
            continue

    return result


def _calendar_year_to_fy(year: int) -> str:
    """Convert a calendar year to Kenya fiscal year label.

    Kenya FY runs July-June, so calendar year 2023 maps to FY 2022/23
    (the FY that *ends* in June 2023). World Bank annual data for 2023
    best maps to FY 2022/23.
    """
    return f"FY {year - 1}/{str(year)[-2:]}"


def _merge_worldbank_data(
    payload: Dict[str, Any],
    wb_data: Dict[str, Dict[str, float]],
) -> Dict[str, Any]:
    """Merge World Bank data into the fixture payload.

    Only fills in None/missing fields — never overwrites existing fixture data
    which is more granular (from Treasury BPS).
    """
    fiscal_years: List[Dict[str, Any]] = payload.get("fiscal_years", [])
    fy_lookup = {fy["fiscal_year"]: fy for fy in fiscal_years}

    for cal_year_str, indicators in wb_data.items():
        try:
            cal_year = int(cal_year_str)
        except ValueError:
            continue

        fy_label = _calendar_year_to_fy(cal_year)
        fy_entry = fy_lookup.get(fy_label)

        if fy_entry is None:
            # Create a new fiscal year entry from WB data
            new_entry: Dict[str, Any] = {"fiscal_year": fy_label}

            # Map WB fields to our schema
            exp_lcu = indicators.get("government_expenditure_lcu")
            if exp_lcu:
                # WB data is in LCU (KES), our fixture is in billions
                new_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            rev_lcu = indicators.get("government_revenue_lcu")
            if rev_lcu:
                new_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

            # Debt service in USD — convert at approximate rate
            ds_usd = indicators.get("total_debt_service_usd")
            if ds_usd:
                # Approximate KES/USD (use rough average)
                kes_rate = 130.0  # conservative average for 2018-2025
                new_entry["debt_service_cost"] = round(
                    ds_usd * kes_rate / 1e9, 1
                )

            ext_debt_usd = indicators.get("external_debt_stocks_usd")
            if ext_debt_usd:
                kes_rate = 130.0
                new_entry["actual_debt"] = round(
                    ext_debt_usd * kes_rate / 1e9, 1
                )

            if len(new_entry) > 1:  # has at least one data field
                new_entry["_source"] = "world_bank_api"
                fiscal_years.append(new_entry)
                fy_lookup[fy_label] = new_entry
        else:
            # Only fill gaps in existing entries
            if fy_entry.get("appropriated_budget") is None:
                exp_lcu = indicators.get("government_expenditure_lcu")
                if exp_lcu:
                    fy_entry["appropriated_budget"] = round(exp_lcu / 1e9, 1)

            if fy_entry.get("total_revenue") is None:
                rev_lcu = indicators.get("government_revenue_lcu")
                if rev_lcu:
                    fy_entry["total_revenue"] = round(rev_lcu / 1e9, 1)

    # Sort fiscal years chronologically
    fiscal_years.sort(key=lambda x: x.get("fiscal_year", ""))
    payload["fiscal_years"] = fiscal_years

    return payload
