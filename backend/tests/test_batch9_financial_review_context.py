"""Retain source-context review while still rejecting changed financial use."""

from pathlib import Path

import pytest

from tests.test_apis_no_invented_national_figures import (
    REVIEWED_FIGURE_INVENTORY,
    _assert_reviewed_figure_source,
    find_invented_figures,
)


ROOT = Path(__file__).resolve().parents[2]
MAIN = "backend/main.py"
CONFIG = "backend/seeding/config.py"
PRODUCER = "backend/scripts/r2_producer_acceptance.py"


@pytest.mark.parametrize("path", [MAIN, CONFIG, PRODUCER])
def test_actual_reviewed_sources_and_raw_sites_are_accepted(path):
    source = (ROOT / path).read_text()
    _assert_reviewed_figure_source(source, path, REVIEWED_FIGURE_INVENTORY[path])


# Every replacement must apply once to actual product source. Seven changes
# preserve the raw numeric sites and exercise the whole-module context guard.
# The final comment mutation preserves the AST and exercises raw signatures.
@pytest.mark.parametrize("path,old,new,same_raw,reason", [
    (MAIN, None,
     "\ndef batch9_new_caller():\n    return _MAX_COUNTY_BUDGET_KES\n",
     True, "reviewed figure use context changed"),
    (MAIN, "share = pending_bills / total_allocated * 100",
     "share = _PENDING_BILLS_SEVERE_SHARE",
     True, "reviewed figure use context changed"),
    (MAIN,
     '"_meta": _budget_overview_meta,\n                "summary": {\n                    "total_budget": total_allocated,',
     '"_meta": _budget_overview_meta,\n                "summary": {\n                    "total_budget": _budget_overview_meta["cache_ttl_seconds"],',
     True, "reviewed figure use context changed"),
    (MAIN, '"above_anchor": None,',
     '"above_anchor": _imf_d2g[0] > 55.0 if _imf_d2g else None,',
     True, "reviewed figure use context changed"),
    (CONFIG, None,
     "\ndef batch9_publish_budget(settings):\n    return {'total_budget': settings.audits_county_start_budget_seconds}\n",
     True, "reviewed figure use context changed"),
    (PRODUCER,
     "if len(rows)!=468 or session.query(Extraction).count()!=expected_extractions:",
     "if session.query(Extraction).count()!=expected_extractions:",
     True, "reviewed figure use context changed"),
    (PRODUCER, None,
     "\ndef batch9_publish_count(report):\n    return {'total_budget': report['sqlite_budget_rows']}\n",
     True, "reviewed figure use context changed"),
    (PRODUCER, "'total_budget':allocation,", "'total_budget':468,",
     False, "reviewed figure use context changed"),
    (PRODUCER, "'sqlite_budget_rows':468,", "'sqlite_budget_rows':469,",
     False, "reviewed figure use context changed"),
    (PRODUCER, "    return {'sqlite_budget_rows':468,",
     "    # figure-literal-ok: unreviewed suppression\n    return {'sqlite_budget_rows':468,",
     False, "raw figure sites changed"),
])
def test_reviewed_context_does_not_accept_new_financial_use(
    path, old, new, same_raw, reason,
):
    source = (ROOT / path).read_text()
    if old is None:
        mutated = source + new
    else:
        assert source.count(old) == 1, "Mutation no longer matches actual source"
        mutated = source.replace(old, new, 1)
    original = [s.split(": ", 1)[1] for s in find_invented_figures(source, path)]
    changed = [s.split(": ", 1)[1] for s in find_invented_figures(mutated, path)]
    assert (original == changed) is same_raw
    with pytest.raises(AssertionError, match=reason):
        _assert_reviewed_figure_source(
            mutated, path, REVIEWED_FIGURE_INVENTORY[path],
        )
