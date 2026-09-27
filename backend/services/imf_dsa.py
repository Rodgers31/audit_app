"""Kenya's risk-of-debt-distress rating, as the IMF and World Bank publish it.

The rating is a published fact. The site used to synthesize it instead:
``/debt/national`` printed "The IMF classifies Kenya at high risk of debt
distress" whenever debt-to-GDP was above 65%, a threshold with no source
(issue #269). Two things went wrong with that. At a ratio of 65.0 the site
said "Moderate" while the IMF said High. And if the IMF re-rated Kenya, the
site would keep attributing the old rating to it for as long as the ratio
stayed above 65.

This module holds the rating verbatim from the joint Bank-Fund Debt
Sustainability Analysis (DSA), with the document, date and page it comes
from. No figure the site computes can change it. Only a newer DSA can.

**Why a declaration and not a fetcher.** imf.org answers 403 to non-browser
clients. On 2026-09-26, ``curl`` of the DSA list got 403 even with a browser
User-Agent, and only an interactive browser could open it. A nightly job
cannot be relied on to confirm the rating is still current. The declaration
therefore records when it was last confirmed
against the IMF's own register (``latest_confirmed``), and every surface
that shows the rating shows its date. A dated rating stays a true statement
after a newer DSA appears. An undated one would not.

**To update.** When the IMF publishes a new Kenya DSA (it will appear in
https://www.imf.org/external/pubs/ft/dsa/dsalist.pdf):

1. Replace the four ``*_verbatim`` fields and ``source``.
2. Refresh ``latest_confirmed``.
3. Replace both extracts under ``backend/tests/fixtures/imf/``.
   ``tests/test_debt_distress_rating_is_sourced.py`` fails until the
   declaration matches the extracts.
"""

from __future__ import annotations

import copy
from datetime import date, datetime, timezone
from typing import Any, Dict

#: Joint World Bank-IMF DSA for Kenya, as printed on its first page.
_KENYA_DSA: Dict[str, Any] = {
    "framework": "Joint World Bank-IMF Debt Sustainability Framework for Low-Income Countries",
    # The four rows of the "Joint Bank-Fund Debt Sustainability Analysis"
    # table, label and value exactly as printed.
    "risk_of_external_debt_distress": "High",
    "overall_risk_of_debt_distress": "High",
    "granularity_in_the_risk_rating": "Sustainable",
    "application_of_judgment": "No",
    "source": {
        "publisher": (
            "International Monetary Fund and International Development "
            "Association (World Bank)"
        ),
        "title": (
            "Kenya: Seventh and Eighth Reviews Under the Extended Fund Facility "
            "and Extended Credit Facility Arrangements — Debt Sustainability "
            "Analysis"
        ),
        "series": "IMF Country Report No. 24/316",
        "url": (
            "https://www.imf.org/-/media/files/publications/cr/2024/english/"
            "1kenea2024003-print-pdf.pdf"
        ),
        # The date printed on the DSA itself.
        "dsa_date": "2024-10-18",
        # "Latest publication date" in the IMF's DSA register (below).
        "published": "2024-11-01",
        # PDF page, i.e. what a PDF viewer's page box takes. It is the DSA's
        # first page, which has no printed number; the next page is printed "2".
        "page": 132,
        "page_label": "PDF p. 132 (first page of the Debt Sustainability Analysis)",
    },
    # The IMF's own register of each country's latest published DSA. This is
    # the evidence that the DSA above was still Kenya's latest on this date.
    "latest_confirmed": {
        "title": "List of LIC DSAs for PRGT-Eligible Countries — As of March 31, 2026",
        "url": "https://www.imf.org/external/pubs/ft/dsa/dsalist.pdf",
        "as_of": "2026-03-31",
        "row": 27,
    },
}


def kenya_dsa_rating(*, today: date | None = None) -> Dict[str, Any]:
    """The declared DSA rating. Each call returns a fresh copy, so a caller
    cannot mutate the declaration."""
    result = copy.deepcopy(_KENYA_DSA)
    today = today or datetime.now(timezone.utc).date()
    age = (today - date.fromisoformat(result["latest_confirmed"]["as_of"])).days
    # This is an app review interval, not an IMF expiry date or a new rating.
    result["freshness"] = {
        "evaluated_on": today.isoformat(),
        "confirmation_age_days": age if age >= 0 else None,
        "review_after_days": 180,
        "status": "unknown" if age < 0 else (
            "confirmation_aging" if age >= 180 else "recent_confirmation"
        ),
        "basis": "App review interval; the dated assessment remains historical evidence, not confirmation of the current rating.",
    }
    return result
