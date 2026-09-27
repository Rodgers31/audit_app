"""``GET /api/v1/audits/federal?top_findings=N`` — the homepage summary, small.

#221 follow-up. The homepage's ``AuditReportsSection`` lists 4 of the
response's findings (the largest STATED amounts) and prints everything else
from summary fields. PR #257 trims the list before it is dehydrated into the
document, but the trim ran in the browser, after the full response had been
downloaded. So whenever the hydrated copy went stale, the client refetch
still pulled the whole list. OBSERVED on production: 139,320 B gzip
(885,732 B decoded) for a document 3,243 s old.

``top_findings`` lets that query ask for the rows it renders. Three properties:

1. SELECTION: the rows are exactly those the frontend's
   ``trimFederalAuditsForHome`` keeps. Both suites read one cases file,
   ``frontend/__tests__/fixtures/federalTopStatedFindings.cases.json``, so the
   two implementations cannot drift apart unseen.
2. SUMMARY: every other field is the full response's, untouched —
   ``total_findings`` still counts all findings, not the rows returned.
3. CACHE: the trimmed and full responses share one cached computation, and
   neither can leak into the other.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CASES_FILE = REPO / "frontend" / "__tests__" / "fixtures" / "federalTopStatedFindings.cases.json"
CASES = json.loads(CASES_FILE.read_text())["cases"]


# ── 1. selection: the shared contract ─────────────────────────────────────


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_selection_matches_the_frontend_contract(case):
    from main import select_top_stated_findings

    picked = select_top_stated_findings(case["findings"], case["n"])
    assert [f["id"] for f in picked] == case["expected_ids"]


def test_selection_does_not_reorder_or_copy_its_input():
    """The full list is the cached payload; selecting from it must not sort it."""
    from main import select_top_stated_findings

    findings = CASES[0]["findings"]
    before = [f["id"] for f in findings]
    select_top_stated_findings(findings, 4)
    assert [f["id"] for f in findings] == before


# ── 2. through the endpoint ───────────────────────────────────────────────

# (provenance amount string, stored amount) per seeded finding. The amounts are
# distinct, so the expected order is fixed by construction, not by the API's
# own ordering of equal severities.
SEEDED = [
    ("KES 3B", 3_000_000_000),
    ("KES 9B", 9_000_000_000),
    ("", None),
    ("KES 0", 0),
    ("KES 1M", 1_000_000),
    ("KES 5B", 5_000_000_000),
]


@pytest.fixture()
def seeded_federal(db_session, seed_country, seed_source_doc):
    from models import Audit, Entity, EntityType, FiscalPeriod, Severity

    entity = Entity(
        id=221,
        country_id=seed_country.id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Top Findings",
        slug="ministry-top-findings-221",
    )
    period = FiscalPeriod(
        id=221,
        country_id=seed_country.id,
        label="FY2023/24",
        start_date=datetime(2023, 7, 1),
        end_date=datetime(2024, 6, 30),
    )
    db_session.add_all([entity, period])
    db_session.flush()
    for i, (label, amount) in enumerate(SEEDED):
        db_session.add(
            Audit(
                entity_id=entity.id,
                period_id=period.id,
                finding_text=f"Finding {i}",
                severity=Severity.WARNING,
                source_document_id=seed_source_doc.id,
                amount=amount,
                audit_year=2023,
                provenance=[{"amount_involved": label}] if label else [{}],
                page_ref=f"p.{100 + i}",
            )
        )
    db_session.commit()


def _full(client):
    r = client.get("/api/v1/audits/federal")
    assert r.status_code == 200
    return r.json()


def _top(client, n):
    r = client.get(f"/api/v1/audits/federal?top_findings={n}")
    assert r.status_code == 200, r.text
    return r.json()


def test_top_findings_returns_only_the_largest_stated_rows(client, seeded_federal):
    top = _top(client, 3)
    assert [f["amount_numeric"] for f in top["findings"]] == [9e9, 5e9, 3e9]


def test_top_findings_rows_are_the_full_responses_rows_untouched(client, seeded_federal):
    full_by_id = {f["id"]: f for f in _full(client)["findings"]}
    for row in _top(client, 3)["findings"]:
        assert row == full_by_id[row["id"]]


def test_every_summary_field_is_the_full_responses(client, seeded_federal):
    full, top = _full(client), _top(client, 3)
    assert len(full["findings"]) == len(SEEDED)
    # `total_findings` describes the report, not the rows this response lists.
    assert top["total_findings"] == len(SEEDED)
    assert {k: v for k, v in top.items() if k != "findings"} == {
        k: v for k, v in full.items() if k != "findings"
    }


def test_without_the_parameter_the_response_is_unchanged(client, seeded_federal):
    """Control: existing callers get every finding, as before."""
    assert len(_full(client)["findings"]) == len(SEEDED)


# ── 3. one cached computation, no leak either way ─────────────────────────
#
# The cache ``set``s a JSON copy of a fresh result but hands back its stored
# object by reference on a HIT. So an implementation that trims the payload in
# place leaks only when the trimmed request is served from the cache: that is
# the full → trimmed → full sequence, which is the one that catches it (checked
# by mutation). Trimmed-first is kept because it is the order a cold homepage
# visit produces.


def test_a_trimmed_request_first_does_not_trim_the_next_full_one(client, seeded_federal):
    assert len(_top(client, 1)["findings"]) == 1
    assert len(_full(client)["findings"]) == len(SEEDED)


def test_full_then_trimmed_then_full(client, seeded_federal):
    assert len(_full(client)["findings"]) == len(SEEDED)
    assert len(_top(client, 2)["findings"]) == 2
    assert len(_full(client)["findings"]) == len(SEEDED)


# ── 4. the parameter is validated, not ignored ────────────────────────────


@pytest.mark.parametrize("bad", ["0", "-1", "101", "four"])
def test_out_of_range_values_are_rejected(client, seeded_federal, bad):
    assert client.get(f"/api/v1/audits/federal?top_findings={bad}").status_code == 422
