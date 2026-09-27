"""Deputy governors, from the Council of Governors (issue #231).

The county page's deputy governor came from ``frontend/lib/data/county-officials.ts``,
typed in for the 2022 cycle. For Meru it said "Isaac Mutuma", who has been
the GOVERNOR since Kawira Mwangaza's impeachment. The Council's API already
says so, so the card showed the same man in both roles. The Council publishes
the deputies too, at /current-deputy-governors/, in the same markup as the
governors page.

Deputies get a different completeness gate from governors. A deputy's seat
can really be vacant after an elevation, an impeachment or a death (Meru's
was, in 2024), so "all 47" would quarantine a correct page. What is still
refused: a county listed twice with two different names, one person listed
for two counties, and a page so short that it has probably changed shape.
"""

import pytest

from seeding.extractors.cog_governors import (
    DEPUTIES_MIN_LISTED,
    KENYAN_COUNTIES,
    GovernorsError,
    parse_deputy_governors,
)
from tests.test_cog_governors import _synthetic, page


def _deputy(county: str) -> str:
    return _synthetic(county).replace("Mwangi", "Wanjiru")


ALL_47 = [(_deputy(c), c) for c in KENYAN_COUNTIES]


def test_a_vacant_seat_is_absent_not_a_failure():
    listed = [(n, c) for n, c in ALL_47 if c != "Homa Bay"]
    result = parse_deputy_governors(page(listed))

    assert len(result.by_county) == 46
    assert "Homa Bay" not in result.by_county
    assert result.missing == ["Homa Bay"]
    assert any("Homa Bay" in c for c in result.checks)


def test_names_are_cleaned_like_governors():
    result = parse_deputy_governors(
        page(
            [("H.E  Eng. Fredrick Kipngetich Kirui", "Kericho")]
            + [p for p in ALL_47 if p[1] != "Kericho"]
        )
    )
    assert result.by_county["Kericho"] == "Fredrick Kipngetich Kirui"


def test_a_short_page_is_quarantined():
    """Below the floor, the page has changed shape; it has not lost 20 deputies."""
    with pytest.raises(GovernorsError) as exc:
        parse_deputy_governors(page(ALL_47[: DEPUTIES_MIN_LISTED - 1]))
    assert exc.value.reason == "too_few_deputies"


def test_one_person_for_two_counties_is_quarantined():
    pairs = [p for p in ALL_47 if p[1] not in ("Meru", "Embu")] + [
        ("H.E Same Person", "Meru"),
        ("H.E Same Person", "Embu"),
    ]
    with pytest.raises(GovernorsError) as exc:
        parse_deputy_governors(page(pairs))
    assert exc.value.reason == "governor_of_two_counties"
