"""County budget aggregation rules, shared by every endpoint that publishes one.

These lived in ``main.py`` and were applied by ``GET /counties`` and
``/counties/{id}/comprehensive``. ``routers/money_flow.py`` could not import
them from there (``main`` imports the router), so it kept its own naive
``sum(allocated_amount)`` over every row — and published Baringo's FY2024/25
budget as KES 26.55B against the Controller of Budget's 9.54B, a 2.78x
overstatement, on the page whose purpose is tracing that money.

The point of a single rule is that it cannot drift. Keeping it here is what
makes that true.
"""

from __future__ import annotations

from typing import Dict, Optional

CLASSIFICATION_CATEGORIES = {"total", "development", "recurrent"}

#: Categories that are neither an economic classification NOR a spending
#: sector, and so belong in neither aggregate. "Own Source Revenue" is money
#: the county RAISED, stored in the same table because it has the same
#: target/actual shape; counting it as expenditure would add a county's
#: revenue to its own spending.
NON_SECTOR_CATEGORIES = {"total budget", "own source revenue"}


def split_classification_and_sector_lines(budget_lines):
    """Split CoB BIRR classification rows from additive sector rows.

    The Controller of Budget's implementation reports carry whole-budget
    ECONOMIC classification rows — Total / Development / Recurrent — alongside
    (modelled) per-sector rows. They describe the same money two ways, so
    summing both double- or triple-counts a county's budget.

    ``GET /counties`` already applied this split; ``/counties/{id}/comprehensive``
    summed every row naively. That did not show up while the two endpoints
    resolved to DIFFERENT fiscal periods — the detail page happened to land on
    a projection period holding only sector rows. Aligning the period selection
    (credibility audit F7) would have exposed it as a tripled county budget, so
    both now go through one rule and cannot drift apart again.

    Returns ``(total_allocated, total_spent, sector_lines, class_by_cat)``.
    """
    sector_lines = []
    class_by_cat: Dict[str, Dict[str, float]] = {}
    for bl in budget_lines:
        cat_key = (bl.category or "").strip().lower()
        if cat_key in CLASSIFICATION_CATEGORIES:
            # Sub-rows (e.g. Personnel Emoluments under Recurrent) are not the
            # aggregate — they would double-count inside the classification.
            if not bl.subcategory:
                agg = class_by_cat.setdefault(cat_key, {"allocated": 0.0, "spent": 0.0})
                agg["allocated"] += float(bl.allocated_amount or 0)
                agg["spent"] += float(bl.actual_spent or 0)
            continue
        if cat_key in NON_SECTOR_CATEGORIES:
            continue
        sector_lines.append(bl)

    # Prefer the CoB "Total" aggregate (real BIRR data). Then the sum of the
    # economic classification. Only then the modelled sector split.
    if class_by_cat.get("total", {}).get("allocated"):
        total_allocated = class_by_cat["total"]["allocated"]
        total_spent = class_by_cat["total"]["spent"]
    elif class_by_cat:
        total_allocated = sum(v["allocated"] for v in class_by_cat.values())
        total_spent = sum(v["spent"] for v in class_by_cat.values())
    else:
        total_allocated = sum(float(b.allocated_amount or 0) for b in sector_lines)
        total_spent = sum(float(b.actual_spent or 0) for b in sector_lines)

    return total_allocated, total_spent, sector_lines, class_by_cat


#: Provenance codes for a county's headline budget figure. The frontend
#: switches its standing provenance note on these, so they are part of the
#: API contract — widen the vocabulary rather than redefining a member.
BUDGET_SOURCE_COB_CBIRR = "cob_cbirr"
BUDGET_SOURCE_CRA_MODEL = "cra_model"


def budget_provenance(class_by_cat, total_allocated) -> Optional[str]:
    """Which kind of row produced the headline budget this response published.

    Both kinds of period live in the database at once — see
    ``tests/test_county_period_agreement``. A CBIRR-reported period carries the
    Controller of Budget's Total / Development / Recurrent classification rows;
    a CRA equitable-share PROJECTION period carries only the modelled sector
    split, and a reader still reaches one through ``?fiscal_year=``.

    The page prints a standing note naming the source of the figure beside it.
    It said "modelled estimate — not official Controller of Budget figures" for
    every county and every period, which is now false for all 47: the CBIRR
    parse reconciles to the report's printed 633,303.87m total. Rather than
    swap one unconditional claim for the other, both endpoints report which
    rows they actually summed and the note follows.

    Returns ``None`` when nothing was published — an absent budget has no
    source, and defaulting it to either label would print a provenance note
    about a figure the page never showed.
    """
    if any(
        class_by_cat.get(cat, {}).get("allocated") for cat in CLASSIFICATION_CATEGORIES
    ):
        return BUDGET_SOURCE_COB_CBIRR
    if total_allocated:
        return BUDGET_SOURCE_CRA_MODEL
    return None


#: Rendered verbatim under the headline figure. Keyed on the code above so the
#: prose and the machine-readable field cannot drift apart.
BUDGET_PROVENANCE_LABELS = {
    BUDGET_SOURCE_COB_CBIRR: (
        "Controller of Budget — County Budget Implementation Review "
        "Report (Total / Development / Recurrent aggregates). The "
        "per-sector split below is modelled from the CRA "
        "equitable-share formula, not read from the CBIRR."
    ),
    BUDGET_SOURCE_CRA_MODEL: (
        "Modelled from the CRA equitable-share formula — NOT "
        "read from Controller of Budget CBIRR tables"
    ),
}
