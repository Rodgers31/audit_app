"""``enhanced_county_extractor`` publishes what answered, or nothing.

The three guards beside this file — ``test_apis_no_invented_national_figures``,
``test_no_published_figure_from_hash_or_clock`` and
``test_apis_no_invented_county_rankings`` — read source text. This one RUNS the
module, with every HTTP call stubbed, and looks at the payload ``main()``
writes. That distinction is the point: a detector can tell you a ``hash()``
call is gone, but only a run can tell you what the module says about Kenya's
counties when none of its sources reply.

Before issue #198 the answer was: quite a lot. With every request failing, the
same run produced 47 county records carrying a population, a budget, a revenue,
a debt, a pending-bills figure, a ``missing_funds`` amount, an ``audit_rating``
and a list of "major issues"; an ``analytics_summary`` totalling KSh 6.0 Bn of
missing county funds; a ``county_rankings`` block ordering all 47, including
"worst_pending_bills"; ``structured_sources_found: 2``, a literal; and a
Nairobi record self-graded ``"data_quality": "high"`` with all three of its
sections empty. Nothing had been fetched.

Two things are pinned here, and they are the same rule from both ends:

* nothing answered must read as nothing answered — a count of 0, an empty
  ``endpoints_answered``, empty sections, and no figure of any kind; and
* something answering must be reported as what it was, naming the endpoint.

``counties_with_a_portal_that_answered`` is counted from the records, not from
``len(self.county_data)``, because a Nairobi record is written whichever way
the requests go — the old ``counties_processed`` would have said 1 for a run in
which every single request failed.

The module is loaded by path. The repo root is deliberately off ``sys.path``
for this suite (see ``conftest.py``: a stub ``seeding/`` package at the root
shadows ``backend/seeding/``), so ``import extractors.county...`` is not
available here.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

requests = pytest.importorskip("requests")

MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "extractors"
    / "county"
    / "enhanced_county_extractor.py"
)

#: Keys that only the withdrawn generator could have put in the payload.
#: ``major_issues`` and ``audit_rating`` are claims about a named county
#: government; the rest are money nobody measured.
WITHDRAWN_KEYS = (
    "analytics_summary",
    "county_rankings",
    "total_missing_funds",
    "average_financial_health",
    "structured_sources_found",
    "missing_funds",
    "audit_rating",
    "major_issues",
    "budget_2025",
    "revenue_2024",
    "debt_outstanding",
    "pending_bills",
    "financial_health_score",
    "per_capita_budget",
    "budget_execution_rate",
    "debt_to_budget_ratio",
    "data_quality",
)


@pytest.fixture(scope="module")
def extractor_class():
    if not MODULE_PATH.is_file():
        pytest.skip(f"{MODULE_PATH.name} has been removed entirely")
    spec = importlib.util.spec_from_file_location("_enhanced_county", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EnhancedCountyDataExtractor


class _Response:
    """The parts of ``requests.Response`` this module touches."""

    def __init__(self, status_code: int, payload=None, text: str = ""):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("response is not JSON")
        return self._payload


def _run(extractor_class, get):
    extractor = extractor_class()
    extractor.session.get = get
    return extractor.run_enhanced_county_extraction()


def _refuse_everything(*_args, **_kwargs):
    raise requests.RequestException("no network in tests")


def test_a_run_where_nothing_answers_publishes_no_figure(extractor_class):
    """Absence stays absence. Not a zero, not an estimate, not a grade.

    The withdrawn-key check comes FIRST on purpose: run this against the
    pre-#198 module and it must fail on what the payload SAYS, not on a
    ``KeyError`` for a summary field that did not exist yet.
    """
    results = _run(extractor_class, _refuse_everything)

    blob = json.dumps(results)
    present = sorted({key for key in WITHDRAWN_KEYS if key in blob})
    assert not present, (
        "a run in which every request failed still published: "
        + ", ".join(present)
    )

    summary = results["extraction_summary"]
    assert summary["counties_with_a_portal_that_answered"] == 0, summary
    assert summary["api_endpoints_discovered"] == 0, summary

    nairobi = results["county_data"]["Nairobi"]
    assert nairobi["endpoints_answered"] == []
    assert nairobi["projects"] == []
    assert nairobi["indicators"] == {}
    assert nairobi["budget_summary"] == {}


def test_the_record_count_is_not_read_as_a_count_of_sources(extractor_class):
    """A record is written either way, so the two numbers must stay apart."""
    results = _run(extractor_class, _refuse_everything)
    summary = results["extraction_summary"]

    assert "counties_processed" not in summary, (
        "counties_processed was len(self.county_data) — a count of records "
        "dressed as a count of counties covered"
    )
    assert summary["county_records_written"] == 1
    assert summary["counties_with_a_portal_that_answered"] == 0
    assert (
        summary["county_records_written"]
        != summary["counties_with_a_portal_that_answered"]
    ), "the record count is standing in for a count of sources that answered"


def test_what_answered_is_reported_as_what_it_was(extractor_class):
    """The other end of the rule: a real reply is passed through, and named."""
    answering_url = "https://nairobi.opencounty.org/api/projects/filters"
    payload = {"projects": [{"id": 1, "title": "Ward road resurfacing"}]}

    def get(url, **_kwargs):
        if url == answering_url:
            return _Response(200, payload)
        return _Response(404, text="not found")

    results = _run(extractor_class, get)

    present = sorted({key for key in WITHDRAWN_KEYS if key in json.dumps(results)})
    assert not present, "one live endpoint brought back: " + ", ".join(present)

    summary = results["extraction_summary"]
    nairobi = results["county_data"]["Nairobi"]

    assert summary["counties_with_a_portal_that_answered"] == 1
    assert nairobi["endpoints_answered"] == [answering_url]
    assert nairobi["projects"] == payload
    # The endpoints that did NOT answer leave their sections empty rather than
    # filled with something plausible.
    assert nairobi["indicators"] == {}
    assert nairobi["budget_summary"] == {}


def test_the_payload_is_writable_as_json(extractor_class):
    """``main()`` json.dumps this straight to disk; a run must not break that."""
    results = _run(extractor_class, _refuse_everything)
    written = json.loads(json.dumps(results))
    assert set(written) == {"extraction_summary", "county_data", "data_sources"}, (
        f"the file main() writes gained or lost a section: {sorted(written)}"
    )
