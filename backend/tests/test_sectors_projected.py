"""Tests for the sectors projection-labelling fix (audit §2.10).

The /sectors page presented FY-in-progress BPS projections as "Public money
actually spent", with no FY/source and no partial-year caveat. The endpoint
must now surface fiscal_year + is_projected/is_partial_year + source, and the
page must label projections (not actuals) with the data provenance shown.
"""

from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"


def test_sectors_endpoint_exposes_fy_and_projected_flag():
    src = (BACKEND_DIR / "main.py").read_text(encoding="utf-8")
    assert '"fiscal_year": dominant_fy,' in src
    assert '"is_partial_year": is_partial_year,' in src
    assert '"is_projected": is_partial_year,' in src
    assert '"source": (' in src  # a source/provenance string is returned


def test_sectors_page_labels_projection_not_actuals():
    page = (FRONTEND_DIR / "app" / "sectors" / "SectorsPageClient.tsx").read_text(
        encoding="utf-8"
    )
    # Provenance + projected caveat are rendered.
    assert "ModelledDataNote" in page
    assert "sectors.projected_note" in page
    assert "sectors.source_label" in page
    # The misleading "actually spent" copy is gone from the i18n.
    msgs = (FRONTEND_DIR / "lib" / "i18n" / "messages.ts").read_text(encoding="utf-8")
    assert "Public money actually spent" not in msgs
    assert "sectors.projected_note" in msgs
