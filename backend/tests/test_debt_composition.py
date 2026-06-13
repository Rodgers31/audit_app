"""Tests for the debt-composition plausibility check (audit 0.4 slice)."""

from __future__ import annotations

from services.trust_guards import check_debt_composition


def test_clean_composition_has_no_notes():
    # external + domestic == total, ratio in band → nothing to flag.
    assert check_debt_composition(
        total=12_000, external=5_500, domestic=6_500, debt_to_gdp=68.0
    ) == []


def test_negative_component_flagged():
    notes = check_debt_composition(total=12_000, external=-1.0, domestic=6_500)
    assert any("negative" in n for n in notes)


def test_components_exceeding_total_flagged():
    notes = check_debt_composition(total=10_000, external=6_000, domestic=6_000)
    assert any("exceed the headline total" in n for n in notes)


def test_uncategorised_gap_flagged():
    notes = check_debt_composition(total=12_000, external=3_000, domestic=3_000)
    assert any("uncategorised" in n for n in notes)


def test_debt_to_gdp_out_of_band_flagged():
    hi = check_debt_composition(
        total=12_000, external=6_000, domestic=6_000, debt_to_gdp=180.0
    )
    assert any("outside the plausible" in n for n in hi)
    ok = check_debt_composition(
        total=12_000, external=6_000, domestic=6_000, debt_to_gdp=68.0
    )
    assert not any("outside the plausible" in n for n in ok)
