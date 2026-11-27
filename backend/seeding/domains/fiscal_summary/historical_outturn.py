"""Qualify the FY2022/23 actuals from two explicitly reviewed Treasury editions."""

from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from services.fiscal_framework_qualification import bind_framework_evidence
from services.fiscal_historical_sources import (
    APDMR_SHA256,
    APDMR_URL,
    NON_TAX_REVENUE_MILLION,
    ORDINARY_REVENUE_MILLION,
    OUTTURN_PAGE,
    OUTTURN_PARSER,
    OUTTURN_SHA256,
    OUTTURN_TITLE,
    OUTTURN_URL,
    REVENUE_BASIS,
    REVENUE_PAGE,
    REVENUE_PARSER,
    REVENUE_SHA256,
    REVENUE_TITLE,
    REVENUE_URL,
    TAX_REVENUE_MILLION,
    YEAR,
)
from services.fiscal_qualification import VERSION, measure_evidence
from services.response_receipts import acquisition_is_intact, copy_receipt, seal_receipt

from .fiscal_framework import (
    FISCAL_FRAMEWORK_BASIS,
    framework_payload,
    gate_column,
    parse_annex_lines,
)

MAX_BYTES = 8_000_000
OUTTURN_FIELDS = {
    "total_borrowing": "total_financing",
    "recurrent_spending": "recurrent",
    "development_spending": "development",
    "county_allocation": "county_transfers",
}
TAX_FIELDS = {
    "tax_revenue": TAX_REVENUE_MILLION,
    "non_tax_revenue": NON_TAX_REVENUE_MILLION,
}
# Independent Table 3A cells, on the same outturn/revenue and financing bases.
ANNEX_TOTALS_MILLION = {
    "ordinary_revenue": ORDINARY_REVENUE_MILLION,
    "total_revenue": 2_360_510,
    "ministerial_aia": 319_391,
    "expenditure": 3_221_001,
    "recurrent": 2_311_564,
    "development": 493_663,
    "county_transfers": 415_774,
    "total_financing": 770_307,
    "net_foreign_financing": 310_759,
    "net_domestic_financing": 459_548,
}

EDITIONS = {
    OUTTURN_URL: (
        OUTTURN_SHA256,
        OUTTURN_PAGE,
        OUTTURN_TITLE,
        OUTTURN_PARSER,
        frozenset(OUTTURN_FIELDS),
    ),
    REVENUE_URL: (
        REVENUE_SHA256,
        REVENUE_PAGE,
        REVENUE_TITLE,
        REVENUE_PARSER,
        frozenset(TAX_FIELDS),
    ),
}


def _read_outturn(path):
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) < OUTTURN_PAGE:
            raise ValueError("historical outturn page missing")
        text = pdf.pages[OUTTURN_PAGE - 1].extract_text() or ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if (
        len(lines) < 4
        or lines[0]
        != "Annex Table 2: Government Operations for the FY 2022/23 - 2029/30 Period, KSh Billion"
        or not re.match(r"^2022/23\s+2023/24\b", lines[1])
        or not any(re.match(r"^Act\.\s+Act\.", header) for header in lines[2:5])
    ):
        raise ValueError("historical outturn period, vintage or units changed")
    split = gate_column(
        parse_annex_lines(lines, page=OUTTURN_PAGE),
        0,
        fiscal_year=YEAR,
        identified_by="printed_actual_column",
    )
    if (
        TAX_REVENUE_MILLION + NON_TAX_REVENUE_MILLION != ORDINARY_REVENUE_MILLION
        or ORDINARY_REVENUE_MILLION + ANNEX_TOTALS_MILLION["ministerial_aia"]
        != ANNEX_TOTALS_MILLION["total_revenue"]
        or any(
            abs(split.values[key] - Decimal(amount) / 1000) > Decimal("0.05")
            for key, amount in ANNEX_TOTALS_MILLION.items()
        )
    ):
        raise ValueError("historical fiscal publications disagree at printed precision")
    return split


def _acquire(client, settings, directory, url):
    digest, _, _, parser, _ = EDITIONS[url]
    target = directory / f"{parser}.pdf"
    client.download_to_file(
        url,
        target,
        max_seconds=min(settings.pdf_download_timeout_seconds, 35),
        max_bytes=min(settings.pdf_download_max_bytes, MAX_BYTES),
        raise_for_status=True,
    )
    with target.open("rb") as contents:
        measured = hashlib.file_digest(contents, "sha256").hexdigest()
    receipt = client.download_receipt(url)
    if (
        measured != digest
        or not acquisition_is_intact(receipt)
        or receipt.get("digest") != digest
        or receipt.get("request_url") != url
        or receipt.get("response_url") != url
        or receipt.get("status") != 200
        or receipt.get("byte_check", {}).get("status") != "matched"
    ):
        raise ValueError("historical fiscal acquisition refused")
    return target, copy_receipt(receipt, parser_version=parser)


def _observations(receipt, source, fields, basis, unit, factor):
    observations = []
    for field, raw in fields.items():
        observations.append(
            {
                "version": 1,
                "source_kind": "pdf",
                "identity": {
                    "measure": field,
                    "entity_id": None,
                    "geography": "KEN",
                    "period": YEAR,
                    "unit": "KES",
                    "basis": basis,
                    "dimensions": {"vintage": "Actual"},
                },
                "raw_value": str(raw),
                "raw_unit": unit,
                "value": str(float(raw * factor)),
                "unit": "KES",
                "locator": {
                    "page": EDITIONS[source["url"]][1],
                    "table": source["table"],
                    "cell": field + " / 2022/23 Actual",
                },
                "transformation": {"operation": "multiply", "factor": str(factor)},
                "checks": {
                    "identity": True,
                    "value": True,
                    "transport": True,
                    "bytes": True,
                    "locator": True,
                },
                "reconciliation": {
                    "status": "matched",
                    "reason": "Treasury actuals reconcile at each publication's printed precision",
                },
            }
        )
    seal_receipt(receipt, observations)
    return [{**item, "_response_receipt": receipt} for item in observations]


def apply_historical_outturn(payload, client, settings):
    """Replace the one historical outturn only after both acquisitions pass."""
    matches = [row for row in payload["fiscal_years"] if row.get("fiscal_year") == YEAR]
    if len(matches) != 1:
        raise ValueError("historical fiscal target missing or ambiguous")
    row = matches[0]
    existing = row.get("fiscal_measure_contract") or {}
    ordinary = existing.get("measures", {}).get("total_revenue") or {}
    if (
        existing.get("version") != VERSION
        or row.get("revenue_basis") != REVENUE_BASIS
        or row.get("total_revenue") != ORDINARY_REVENUE_MILLION / 1000
        or ordinary.get("source", {}).get("sha256") != APDMR_SHA256
        or ordinary.get("source", {}).get("url") != APDMR_URL
        or ordinary.get("fiscal_year") != YEAR
        or ordinary.get("basis") != REVENUE_BASIS
        or ordinary.get("vintage") != "Preliminary"
        or ordinary.get("precision_kes") != 1_000_000
        or ordinary.get("value_kes") != ORDINARY_REVENUE_MILLION * 1_000_000
    ):
        raise ValueError(
            "historical revenue differs from the reviewed APDMR denominator"
        )
    with TemporaryDirectory(prefix="fiscal-actuals-") as scratch:
        brop, brop_receipt = _acquire(client, settings, Path(scratch), OUTTURN_URL)
        _, annex_receipt = _acquire(client, settings, Path(scratch), REVENUE_URL)
        split = _read_outturn(brop)

    framework = framework_payload(split, source_url=OUTTURN_URL, page=OUTTURN_PAGE)
    framework["source"].update(
        title=OUTTURN_TITLE,
        sha256=OUTTURN_SHA256,
        column="Actual",
        page=f"Annex Table 2, PDF p.{OUTTURN_PAGE}",
        table="Annex Table 2: Government Operations (KSh billion)",
    )
    bind_framework_evidence(framework)
    annex_source = {
        "publisher": "The National Treasury",
        "title": REVENUE_TITLE,
        "url": REVENUE_URL,
        "sha256": REVENUE_SHA256,
        "column": "Actual",
        "page": f"Table 3A, PDF p.{REVENUE_PAGE}",
        "table": "Table 3A: Government Budget and Public Debt (KSh million)",
        "measure": (
            "Published ordinary-revenue components, excluding A-in-A. "
            "The Treasury footnote identifies AMISOM grants within Other Taxes."
        ),
    }
    candidate = deepcopy(row)
    measures = candidate["fiscal_measure_contract"]["measures"]
    payments = {field: split.values[key] for field, key in OUTTURN_FIELDS.items()}
    for field, value in payments.items():
        candidate[field] = float(value)
        measures[field] = measure_evidence(
            float(value * 1_000_000_000),
            YEAR,
            FISCAL_FRAMEWORK_BASIS,
            "Actual",
            100_000_000,
            dict(framework["source"]),
        )
    for field, amount in TAX_FIELDS.items():
        candidate[field] = amount / 1000
        measures[field] = measure_evidence(
            amount * 1_000_000,
            YEAR,
            REVENUE_BASIS,
            "Actual",
            1_000_000,
            dict(annex_source),
        )
    candidate.update(
        fiscal_framework=framework,
        split_basis=FISCAL_FRAMEWORK_BASIS,
        historical_outturn_evidence=[
            *_observations(
                brop_receipt,
                framework["source"],
                payments,
                FISCAL_FRAMEWORK_BASIS,
                "billion_KES",
                1_000_000_000,
            ),
            *_observations(
                annex_receipt,
                annex_source,
                TAX_FIELDS,
                REVENUE_BASIS,
                "million_KES",
                1_000_000,
            ),
        ],
    )
    candidate.pop("tax_split_absent_reason", None)
    candidate.pop("fiscal_framework_absent_reason", None)
    row.clear()
    row.update(candidate)
