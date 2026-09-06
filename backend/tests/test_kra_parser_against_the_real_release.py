"""The KRA head extractor, run against the page it actually reads.

`test_kra_revenue_overlay.py` exercises the extractor on hand-written prose
containing only well-behaved sentences. The live page contains one that is
not, and it has silently defeated the parse on every run since the overlay was
switched on — 20 consecutive nightlies reporting::

    [WARN] revenue_by_source ingestion: only a SECONDARY series refreshed in
    all 20 recent run(s); the published figure is still a fixture
    (reasons: kra_overlay_not_promoted(failed_validation))

The extractor takes, for each head, the money figure NEAREST any occurrence of
that head's name. KRA's FY2024/25 release contains::

    Significant amounts of adjustment vouchers were utilized across various tax
    heads, with Corporation Tax accounting for Kshs 28.622 Billion, PAYE for
    Kshs 10.422 Billion, and Domestic VAT for Kshs 6.510 Billion, among others.

Three heads named with a figure right beside each — distances 9, 32 and 9 —
which beat the real collection sentences, where the money sits further from the
head's name. Those figures are ADJUSTMENT VOUCHERS, not collections. Excise
separately picks up a betting-tax *surplus* of 1.945B instead of Domestic
Excise's 69.385B collection.

Measured against the live page (2026-09-06): PAYE 10.422 (actual 560.963),
Corporation Tax 28.622 (304.833), VAT 6.510 (327.336), Excise 1.945 (69.385).
Only Customs was right. The heads summed to 927B against an expected 2,323B, so
``check_revenue_breakdown`` quarantined the parse and the fixture stood — the
gate did its job, which is why nothing worse than a WARN ever appeared.

The distinction the parser was missing is semantic, not positional: the figure
we want is a COLLECTION. KRA states it with a collection verb ("collected",
"collection stood at", "with a collection of"); the distractors are qualified
as vouchers, targets, surpluses, or half-year splits.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from seeding.domains.revenue_by_source.fetcher import _overlay_kra_breakdown
from seeding.domains.revenue_by_source.kra_parser import (
    extract_kra_fiscal_year,
    extract_kra_revenue_by_type_from_text,
)

FIXTURE = Path(__file__).parent / "fixtures" / "kra" / "fy2024_25_press_release.txt"

#: What the release actually reports, read off the page by hand.
PUBLISHED = {
    "PAYE": Decimal("560.963"),
    "Corporation Tax": Decimal("304.833"),
    "VAT": Decimal("327.336"),
    "Excise Duty": Decimal("69.385"),
    "Customs & Import Duty": Decimal("879.329"),
}


@pytest.fixture(scope="module")
def release_text() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class TestTheRealRelease:
    def test_the_fiscal_year_is_read_correctly(self, release_text):
        """This part always worked — pinned so the fix cannot regress it."""
        assert extract_kra_fiscal_year(release_text) == "FY 2024/25"

    @pytest.mark.parametrize("head", sorted(PUBLISHED))
    def test_each_head_matches_what_kra_published(self, release_text, head):
        got = extract_kra_revenue_by_type_from_text(release_text)
        assert head in got, f"{head} not extracted at all"
        assert got[head] == PUBLISHED[head], (
            f"{head}: parsed {got[head]}B, KRA published {PUBLISHED[head]}B"
        )

    def test_the_voucher_sentence_is_not_mistaken_for_collections(
        self, release_text
    ):
        """The specific trap: 28.622 / 10.422 / 6.510 are adjustment vouchers."""
        got = extract_kra_revenue_by_type_from_text(release_text)
        for bad in (Decimal("28.622"), Decimal("10.422"), Decimal("6.510")):
            assert bad not in got.values(), (
                f"{bad}B is an adjustment-voucher figure, not a collection: {got}"
            )

    def test_excise_is_the_domestic_collection_not_the_betting_surplus(
        self, release_text
    ):
        got = extract_kra_revenue_by_type_from_text(release_text)
        assert got.get("Excise Duty") != Decimal("1.945")


class TestTheOverlayPromotes:
    """End to end: a correct parse must clear the trust gate."""

    def test_the_breakdown_reconciles_and_is_promoted(self, release_text):
        payload = json.loads(
            (
                Path(__file__).parents[1]
                / "seeding"
                / "real_data"
                / "revenue_by_source.json"
            ).read_text(encoding="utf-8")
        )
        by_type = {
            k: float(v)
            for k, v in extract_kra_revenue_by_type_from_text(release_text).items()
        }
        fy = extract_kra_fiscal_year(release_text)
        _, status = _overlay_kra_breakdown(payload, by_type, fy)
        assert status.startswith("promoted"), (
            f"a faithful parse of the real release must clear the gate, got "
            f"{status!r} from {by_type}"
        )

    def test_the_promoted_rows_carry_kra_values(self, release_text):
        payload = json.loads(
            (
                Path(__file__).parents[1]
                / "seeding"
                / "real_data"
                / "revenue_by_source.json"
            ).read_text(encoding="utf-8")
        )
        by_type = {
            k: float(v)
            for k, v in extract_kra_revenue_by_type_from_text(release_text).items()
        }
        out, _ = _overlay_kra_breakdown(
            payload, by_type, extract_kra_fiscal_year(release_text)
        )
        rows = {
            r["revenue_type"]: r
            for r in out
            if r.get("fiscal_year") == "FY 2024/25"
        }
        assert rows["PAYE"]["amount_billion_kes"] == 561.0
        assert rows["PAYE"]["_revenue_source"] == "kra_live"
