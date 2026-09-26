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
from typing import Any, Dict, List, Optional

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
    from ...freshness import mark_fixture, mark_live, mark_partial

    live_records: List[Dict[str, Any]] = []
    wb_reason = "worldbank_disabled"

    # Step 1: Try World Bank API
    if settings.enrich_with_worldbank:
        wb_reason = "worldbank_returned_nothing"
        try:
            live_records = _fetch_wb_revenue(client, settings)
            if live_records:
                logger.info(
                    "Fetched %d revenue records from World Bank", len(live_records)
                )
        except Exception as exc:
            logger.warning("World Bank revenue fetch failed: %s", exc)
            wb_reason = f"worldbank_unreachable({type(exc).__name__})"

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

    # Step 4: live KRA per-tax-head overlay. The newest ANNUAL release is
    # DISCOVERED each run (kra_discovery) — the configured
    # ``settings.kra_revenue_url`` is one candidate among several, no longer
    # the only source. Only a release that passes validation against KRA's
    # own totals replaces anything; otherwise the fixture breakdown stands.
    try:
        final_payload, kra_status = _apply_kra_live(final_payload, client, settings)
        logger.info("revenue_by_source KRA overlay: %s", kra_status)
    except Exception as exc:
        kra_status = f"error({type(exc).__name__})"
        logger.warning("KRA revenue overlay skipped: %s", exc)

    # Provenance. The per-tax-head breakdown (PAYE / VAT / Corporation /
    # Excise / Customs) is the figure this domain actually publishes, and it
    # comes ONLY from KRA. World Bank supplies headline totals that do not
    # touch the breakdown, so a World-Bank-only run is recorded as live with a
    # detail that says the breakdown is still fixture — the same distinction
    # fiscal_summary draws for its headline budget. "promoted" says the
    # overlay applied; whether it applied the publisher's NEWEST edition is
    # judged separately by seeding/edition_gates.py (#243: this printed
    # "promoted:5/FY 2024/25" and LIVE for eleven weeks after KRA published
    # FY 2025/26).
    kra_promoted = kra_status.startswith("promoted")
    detail = f"World Bank: {len(live_records)} record(s); KRA overlay: {kra_status}"
    if kra_promoted:
        mark_live("revenue_by_source", detail=detail)
    elif live_records:
        # PARTIAL, not live. Reported by review on PR #136: the World Bank
        # totals are genuinely fresh, but the per-tax-head breakdown is what
        # this domain publishes, and it is still the fixture. Recording LIVE
        # made check_ingestion_freshness report OK, so KRA could stay
        # unavailable indefinitely behind a green nightly.
        mark_partial(
            "revenue_by_source",
            reason=f"kra_overlay_not_promoted({kra_status})",
            detail=f"World Bank headline totals only; tax-head breakdown still fixture. {detail}",
        )
    else:
        mark_fixture("revenue_by_source", reason=wb_reason, detail=detail)

    return final_payload


def _response_text(resp: Any, url: str) -> str:
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


# ─────────────────────────────────────────────────────────────────────────
# Discovery of KRA's newest annual release (#243)
# ─────────────────────────────────────────────────────────────────────────


def _get_or_none(client: SeedingHttpClient, url: str) -> Optional[Any]:
    """GET ``url``; ``None`` for a 4xx/5xx or a transport error. Probing a
    slug that does not exist yet is normal, not a failure."""
    try:
        resp = client.get(url, raise_for_status=False)
    except Exception as exc:
        logger.info("KRA candidate unreachable (%s): %s", url, exc)
        return None
    status = getattr(resp, "status_code", 200)
    if status >= 400:
        logger.info("KRA candidate %s -> HTTP %s", url, status)
        return None
    return resp


def _read_release(client: SeedingHttpClient, url: str, hinted_fy: Optional[str]):
    """Read one candidate page as a KraRelease (dashboard or prose), or None."""
    from urllib.parse import urljoin

    from .kra_discovery import (
        HeadFigure,
        KraRelease,
        iframe_src,
        module_script_src,
        parse_dashboard_bundle,
    )
    from .kra_parser import extract_kra_fiscal_year, extract_kra_revenue_by_type_from_text

    resp = _get_or_none(client, url)
    if resp is None:
        return None
    html = resp.text if "pdf" not in (resp.headers.get("content-type") or "").lower() else ""
    frame = iframe_src(html)
    if frame:
        frame_url = urljoin(url, frame)
        shell = _get_or_none(client, frame_url)
        script = module_script_src(shell.text) if shell is not None else None
        if script:
            bundle_url = urljoin(frame_url, script)
            bundle = _get_or_none(client, bundle_url)
            if bundle is not None:
                release = parse_dashboard_bundle(bundle.text, url=url, data_url=bundle_url)
                if release is not None:
                    return release
        logger.warning("KRA page %s embeds %s but no release data was read", url, frame)
        return None

    text = _response_text(resp, url)
    heads = extract_kra_revenue_by_type_from_text(text)
    fy = extract_kra_fiscal_year(text) or hinted_fy
    if not heads or not fy:
        return None
    return KraRelease(
        fiscal_year=fy,
        url=url,
        shape="press_release",
        heads={k: HeadFigure(amount_bn=v) for k, v in heads.items()},
    )


def discover_kra_releases(
    client: SeedingHttpClient, settings: SeedingSettings, today: Optional[Any] = None
) -> tuple[List[Any], Optional[str], Optional[str]]:
    """Every readable annual release candidate, plus the newest FY the
    publisher is SEEN to have (for the edition gate) and where.

    An annual-performance slug that answers 200 counts as seen even if its
    data cannot be read — that is exactly the case the gate must go red on.
    """
    from datetime import date as _date

    from .kra_discovery import LISTING_URL, fy_from_text, listing_candidates, slug_candidates

    today = today or _date.today()
    releases: List[Any] = []
    seen: List[tuple[str, str]] = []

    for fy, url in slug_candidates(today):
        if _get_or_none(client, url) is None:
            continue
        seen.append((fy, url))
        release = _read_release(client, url, fy)
        if release is not None:
            releases.append(release)

    listing = _get_or_none(client, LISTING_URL)
    if listing is not None:
        # The three newest July-September revenue releases: enough to cover a
        # year whose result KRA posts as several near-duplicate releases.
        for _published, _title, url in listing_candidates(listing.text)[:3]:
            release = _read_release(client, url, None)
            if release is not None and len(release.heads) >= 4:
                releases.append(release)
                seen.append((release.fiscal_year, url))

    if settings.kra_revenue_url:
        release = _read_release(client, settings.kra_revenue_url, fy_from_text(settings.kra_revenue_url))
        if release is not None:
            releases.append(release)
            seen.append((release.fiscal_year, settings.kra_revenue_url))

    newest_seen = max(seen, key=lambda t: t[0]) if seen else (None, None)
    return releases, newest_seen[0], newest_seen[1]


def _apply_kra_live(
    payload: List[Dict[str, Any]],
    client: SeedingHttpClient,
    settings: SeedingSettings,
) -> tuple[List[Dict[str, Any]], str]:
    """Discover, validate and overlay the newest KRA annual release."""
    from ...freshness import record_publisher_edition
    from .kra_discovery import DATASET, validate_release

    releases, newest_fy, newest_url = discover_kra_releases(client, settings)
    if newest_fy:
        record_publisher_edition(
            "revenue_by_source", dataset=DATASET, edition=newest_fy, url=newest_url
        )
    if not releases:
        return payload, "no_release_found"

    # Newest FY first; within a FY prefer the structured dashboard to prose.
    releases.sort(key=lambda r: (r.fiscal_year, r.shape == "dashboard"), reverse=True)
    reasons: List[str] = []
    for release in releases:
        problems = validate_release(release)
        if problems:
            reasons.append(f"{release.fiscal_year} {release.shape}: {problems[0]}")
            logger.warning(
                "KRA %s release %s refused: %s", release.fiscal_year, release.url, problems
            )
            continue
        if release.shape == "dashboard":
            out, status = _overlay_kra_release(payload, release)
        else:
            by_type = {k: float(v.amount_bn) for k, v in release.heads.items()}
            out, status = _overlay_kra_breakdown(
                payload, by_type, release.fiscal_year, source_url=release.url
            )
        if not status.startswith("promoted"):
            reasons.append(f"{release.fiscal_year} {release.shape}: {status}")
            continue
        if newest_fy and release.fiscal_year != newest_fy:
            # An OLDER edition promoted while KRA's newest failed. The first
            # live run of this code did exactly that — the FY 2025/26 bundle
            # read no heads, FY 2024/25's prose promoted, and the run called
            # itself LIVE. It must not read as success: the status no longer
            # starts with "promoted", so the domain records PARTIAL.
            return out, (
                f"newest_edition_not_promoted({newest_fy}: "
                f"{'; '.join(reasons) or 'no readable release'}); older {status}"
            )
        return out, status
    return payload, "failed_validation: " + "; ".join(reasons)


def _q(value: Any, places: str = "0.01") -> float:
    """Half-up to the column's scale (amounts are NUMERIC(15,2)), so the live
    overlay and the fixture it refreshes round the same figure the same way —
    float ``round(355.255, 2)`` gives 355.25, the column would store 355.26."""
    from decimal import ROUND_HALF_UP, Decimal

    return float(Decimal(str(value)).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def _fmt_bn(value: Any) -> str:
    return f"{float(value):,.3f}".rstrip("0").rstrip(".")


def _row_for(payload: List[Dict[str, Any]], fiscal_year: str, revenue_type: str) -> Dict[str, Any]:
    """The payload row for (FY, head), created if the FY has none yet — a
    release for a year the fixture never listed must land on ITS year."""
    for r in payload:
        if r.get("fiscal_year") == fiscal_year and r.get("revenue_type") == revenue_type:
            return r
    row: Dict[str, Any] = {
        "fiscal_year": fiscal_year,
        "revenue_type": revenue_type,
        "category": "tax",
        "amount_billion_kes": None,
        "target_billion_kes": None,
        "performance_pct": None,
        "share_of_total_pct": None,
        "yoy_growth_pct": None,
    }
    payload.append(row)
    return row


def _stamp_published(
    row: Dict[str, Any],
    amount: float,
    note: str,
    source_url: Optional[str],
    places: str = "0.01",
) -> None:
    """Set a published amount and EVERYTHING that describes it. A promoted row
    must not keep the fixture's projection target, or a note describing a
    number it no longer holds.

    A row that is ALREADY published at this amount keeps its note: the
    fixture's notes on those rows carry more than the prose parse can
    (performance, growth, target), and re-promoting the same figure every
    night must not strip them."""
    new_amount = _q(amount, places)
    if row.get("basis") == "published" and row.get("amount_billion_kes") is not None:
        try:
            unchanged = abs(float(row["amount_billion_kes"]) - new_amount) < 0.05
        except (TypeError, ValueError):
            unchanged = False
        if unchanged:
            row["amount_billion_kes"] = new_amount
            row["data_quality"] = "official"
            row["_revenue_source"] = "kra_live"
            return
    if row.get("basis") == "projected":
        # The fixture's target, performance and share on a projected row are
        # house projections, not KRA's; they cannot sit beside a KRA actual.
        row["target_billion_kes"] = None
        row["performance_pct"] = None
        row["share_of_total_pct"] = None
    row["amount_billion_kes"] = new_amount
    row["basis"] = "published"
    row["notes"] = note
    row["data_quality"] = "official"
    row["_revenue_source"] = "kra_live"
    if source_url:
        row["source_url"] = source_url


def _overlay_kra_release(
    payload: List[Dict[str, Any]], release: Any
) -> tuple[List[Dict[str, Any]], str]:
    """Overlay a VALIDATED dashboard release onto its own fiscal year. Pure."""
    from .kra_discovery import PUBLISHED_HEADS, RESIDUAL_HEAD, residual_bn

    fy = release.fiscal_year
    label = f"KRA Annual Revenue Performance {fy}"
    for head in PUBLISHED_HEADS:
        fig = release.heads[head]
        row = _row_for(payload, fy, head)
        bits = [f"{label}: {head} collected KES {_fmt_bn(fig.amount_bn)}B"]
        if fig.target_bn is not None:
            bits[0] += f" vs target {_fmt_bn(fig.target_bn)}B"
        if fig.performance_pct is not None:
            bits.append(f"performance {fig.performance_pct}%")
        if fig.growth_pct is not None:
            bits.append(f"growth {fig.growth_pct}%")
        _stamp_published(row, float(fig.amount_bn), ", ".join(bits), release.url)
        # KRA's own statements for this head, or nothing — never the fixture's.
        row["target_billion_kes"] = _q(fig.target_bn) if fig.target_bn is not None else None
        row["performance_pct"] = _q(fig.performance_pct, "0.1") if fig.performance_pct is not None else None
        row["yoy_growth_pct"] = _q(fig.growth_pct, "0.1") if fig.growth_pct is not None else None
        # Share of EXCHEQUER revenue, the base the earlier years' shares use
        # (FY 2024/25 PAYE 24.1 = 561.0 / 2,323).
        row["share_of_total_pct"] = (
            _q(fig.amount_bn / release.exchequer_bn * 100, "0.1")
            if release.exchequer_bn
            else None
        )

    residual = residual_bn(release)
    if residual is not None:
        row = _row_for(payload, fy, RESIDUAL_HEAD)
        row["amount_billion_kes"] = _q(residual)
        row["basis"] = "residual"
        row["share_of_total_pct"] = _q(residual / release.exchequer_bn * 100, "0.1")
        row["target_billion_kes"] = None
        row["performance_pct"] = None
        row["yoy_growth_pct"] = None
        row["data_quality"] = "official"
        row["_revenue_source"] = "kra_live"
        row["source_url"] = release.url
        row["notes"] = (
            f"Residual: Exchequer {_fmt_bn(release.exchequer_bn)}B minus identified "
            f"tax heads ({label}). Includes withholding tax, capital gains, stamp "
            f"duty, digital economy and betting taxes."
        )
    # else: the release states no exchequer figure — the residual row keeps
    # whatever it held; it is never set to 0.
    applied = len(PUBLISHED_HEADS)
    return payload, f"promoted:{applied}/{fy} (dashboard{', residual' if residual is not None else ''})"


def _overlay_kra_breakdown(
    payload: List[Dict[str, Any]],
    by_type: Dict[str, float],
    fiscal_year: Optional[str],
    *,
    source_url: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], str]:
    """Validate ``by_type`` (read from a press release's prose) and overlay it
    onto the tax rows of ``fiscal_year``. Pure; no network. Returns
    ``(payload, status)``.

    It used to fall back to the NEWEST fixture year when the release's year
    was not in the payload, which would have stamped a FY 2026/27 release onto
    FY 2025/26 rows (#243). A release lands on its own year or not at all.
    """
    if not by_type:
        return payload, "no_live_value"
    if not fiscal_year:
        return payload, "no_fiscal_year"

    tax_rows = [
        r
        for r in payload
        if str(r.get("category", "tax")).lower() == "tax" and r.get("fiscal_year")
    ]
    fy_rows = [r for r in tax_rows if r["fiscal_year"] == fiscal_year]

    def _amt(r: Dict[str, Any]) -> float:
        # Amounts only. A projected row's target is a house projection, and
        # reconciling KRA's actuals against it refused FY 2025/26 (2,352B vs
        # a projected 2,815B) for being unlike a guess.
        v = r.get("amount_billion_kes")
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    expected_total = sum(_amt(r) for r in fy_rows) or None
    if expected_total is None:
        # A year the payload does not list, or lists only as projections:
        # nothing measured to reconcile the prose against, so require the
        # complete set of heads instead.
        from .kra_discovery import PUBLISHED_HEADS

        missing = [h for h in PUBLISHED_HEADS if h not in by_type]
        if missing:
            return payload, f"failed_validation: new year {fiscal_year} lacks {missing}"

    from services.trust_guards import check_revenue_breakdown

    notes = check_revenue_breakdown(by_type, expected_total)
    if notes:
        # Carry WHY into the status. It reaches the nightly through
        # mark_partial's reason, and "failed_validation" on its own named
        # nothing: the parse was wrong by a factor of 54 on PAYE for 20
        # consecutive runs and the log said only that a check had failed.
        return payload, f"failed_validation: {notes[0]}"

    by_name = {r.get("revenue_type"): r for r in fy_rows}
    applied = 0
    for rtype, amount in by_type.items():
        rec = by_name.get(rtype)
        if rec is None and expected_total is not None:
            continue  # a measured year: only refresh heads it already lists
        if rec is None:
            rec = _row_for(payload, fiscal_year, rtype)
        # Re-base the row along with its amount — and its note: the fixture's
        # ``basis`` and ``notes`` describe the figure the fixture carried; the
        # number here is KRA's own, freshly parsed from the release. Leaving
        # the old basis would caption a published collection as a projection
        # or a derivation — the page reads this field to decide what to tell
        # the reader about the figure.
        _stamp_published(
            rec,
            amount,
            f"KRA Annual Revenue Performance {fiscal_year}: {rtype} collected "
            f"KES {_fmt_bn(amount)}B",
            source_url,
            # One decimal, as this path has always stored the prose figures
            # (FY 2024/25 PAYE 560.963 -> 561.0); unchanged by #243.
            places="0.1",
        )
        applied += 1

    return payload, (f"promoted:{applied}/{fiscal_year}" if applied else "no_match")
