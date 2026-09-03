"""Tests for the sectors endpoint's projection labelling (audit §2.10), and
for the withdrawal of the page that consumed it (credibility audit F11).

Original defect: the /sectors page presented FY-in-progress BPS projections as
"Public money actually spent", with no FY/source and no partial-year caveat.
The endpoint fix — surfacing fiscal_year + is_projected/is_partial_year +
source — still stands and is still pinned below.

The page-level half of that fix has been superseded. Labelling was never going
to be enough, because the numbers underneath it are not sector data at all:
across all 47 counties there is exactly ONE distinct set of sector shares
(Health 25%, Education 20%, Roads 15%, Water 10%, Agriculture 8%,
Administration 7%, Trade 5%, Environment 4%, Social 3%, Other 3%) — a fixed
template applied to each county's headline budget. /sectors rendered that
template under the title "WHERE COUNTIES ACTUALLY SPEND", beside a methodology
box describing a label-normalisation step that cannot be running, since every
county already carries the same ten labels in the same proportions.

So the page was removed rather than relabelled. The old assertion (that
SectorsPageClient.tsx renders a projected-note) is replaced by one that the
route does not come back without the underlying extraction — otherwise this
test would quietly re-bless the template the moment someone restored the file.
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


def test_sectors_page_stays_withdrawn():
    """The /sectors route must not exist while the split behind it is a template.

    Restoring the page means restoring a chart whose ten shares are identical
    for every county in Kenya. If someone adds the route back, this fails and
    they have to say what changed in the extraction.
    """
    assert not (FRONTEND_DIR / "app" / "sectors").exists(), (
        "app/sectors was withdrawn (credibility audit F11) because county "
        "sector_breakdown is a fixed 25/20/15/10/8/7/5/4/3/3 template, not "
        "extracted sector lines. Restore the route only together with a real "
        "extraction from CoB CBIRR sector tables — and prove it by asserting "
        "here that two counties have DIFFERENT sector shares."
    )


def test_misleading_actually_spent_copy_stays_out_of_the_i18n():
    """The original §2.10 defect, still pinned: whatever replaces the page must
    not describe modelled allocations as money actually spent."""
    msgs = (FRONTEND_DIR / "lib" / "i18n" / "messages.ts").read_text(encoding="utf-8")
    assert "Public money actually spent" not in msgs
