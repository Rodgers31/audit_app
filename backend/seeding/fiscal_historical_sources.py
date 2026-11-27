"""Reviewed Treasury source identities for the FY2022/23 actual outturn."""

YEAR = "FY 2022/23"
APDMR_URL = (
    "https://www.treasury.go.ke/sites/default/files/Annual%20borrowing/"
    "Annual-Public-Debt-Report-2022-2023-Sept-2023.pdf"
)
APDMR_SHA256 = "00cf5f2e12e6b6733110d66e130404f63824b42d413b5a67b0250ec734f6eb1e"
OUTTURN_URL = "https://www.treasury.go.ke/sites/default/files/2025-Budget-Review-and-Outlook-Paper-1.pdf"
OUTTURN_SHA256 = "e0479eca5a318aa97d6daf11672880433b7d6a4686a09fa3d4895e09d93cf1f4"
OUTTURN_PAGE = 56
OUTTURN_TITLE = "2025 Budget Review and Outlook Paper"
REVENUE_URL = (
    "https://www.treasury.go.ke/sites/default/files/Statistical%20Annex%20to%20the%20Budget%20Statement/"
    "Statistical%20Annex%20to%20the%20Budget%20Statement%20for%20the%20FY%202026-27.pdf"
)
REVENUE_SHA256 = "8847f557e9663e06ab8e070427449f11d7d8b53502f256500302c6fea12f609f"
REVENUE_PAGE = 11
REVENUE_TITLE = "FY2026/27 Budget Statement Statistical Annex"
OUTTURN_PARSER = "fiscal-2022-23-brop-outturn-v1"
REVENUE_PARSER = "fiscal-2022-23-statistical-annex-v1"
REVENUE_BASIS = "ordinary_revenue_excl_aia"
# Reviewed printed cells from Table 3A's 2022/23 column, in KSh million.
# The image-only edition is checked by exact SHA-256 before using these cells.
ORDINARY_REVENUE_MILLION = 2_041_119
TAX_REVENUE_MILLION = 1_961_974
NON_TAX_REVENUE_MILLION = 79_145


def matching_historical_tax_split(year, proofs):
    """Permit the exact published split alongside the identical APDMR denominator."""
    if year != YEAR:
        return False
    total = proofs["total_revenue"]
    if (
        total["source"]["url"],
        total["source"]["sha256"],
        total["vintage"],
        total["basis"],
        total["precision_kes"],
        total["value_kes"],
    ) != (
        APDMR_URL,
        APDMR_SHA256,
        "Preliminary",
        REVENUE_BASIS,
        1_000_000,
        ORDINARY_REVENUE_MILLION * 1_000_000,
    ):
        return False
    for field, amount in (
        ("tax_revenue", TAX_REVENUE_MILLION),
        ("non_tax_revenue", NON_TAX_REVENUE_MILLION),
    ):
        proof = proofs[field]
        if (
            proof["source"]["url"],
            proof["source"]["sha256"],
            proof["source"]["page"],
            proof["vintage"],
            proof["basis"],
            proof["precision_kes"],
            proof["value_kes"],
        ) != (
            REVENUE_URL,
            REVENUE_SHA256,
            f"Table 3A, PDF p.{REVENUE_PAGE}",
            "Actual",
            REVENUE_BASIS,
            1_000_000,
            amount * 1_000_000,
        ) or not (
            proof.get("source_document_id") and proof.get("extraction_id")
        ):
            return False
    return True
