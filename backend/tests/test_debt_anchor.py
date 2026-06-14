"""Tests for the debt-anchor fix (audit §3.7).

The site framed debt as "% of the KES 10T ceiling" and warned "ceiling
breached by 25%". That numeric ceiling was repealed by the PFM (Amendment)
Act 2023 and replaced with a 55%-of-GDP (present-value) anchor. /fiscal/
summary must now serve the anchor, and the homepage card must key off it
rather than the repealed ceiling's usage %.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


def test_fiscal_summary_serves_55pct_anchor_and_repealed_flag():
    src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    assert '"anchor_pct_gdp": 55.0' in src
    assert '"former_ceiling_repealed": True' in src
    assert '"debt_anchor": debt_anchor,' in src
    # Debt-to-GDP for the anchor comparison comes from the authoritative IMF
    # series, not the repealed numeric ceiling.
    assert "_latest_imf_debt_to_gdp(db)" in src


def test_herosection_keys_off_anchor_not_repealed_ceiling():
    src = (FRONTEND_DIR / "components" / "dashboard" / "HeroSection.tsx").read_text(
        encoding="utf-8"
    )
    # Uses the anchor block...
    assert "debt_anchor" in src
    assert "anchorLine" in src
    # ...and no longer keys the gauge off the repealed 10T ceiling usage %.
    assert "debt_ceiling_usage_pct" not in src
    assert "ceilingRaw" not in src
