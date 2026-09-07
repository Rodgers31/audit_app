"""A committed JSON fixture may not declare a population it does not hold, and
may not sort named counties into a good half and a bad half.

Issue #196 found ``apis/enhanced_cob_extraction_results.json`` opening with::

    "extraction_metadata": {
      "source": "Controller of Budget Reports",
      "extraction_date": "2024-08-24",
      "report_period": "FY 2023/24",
      "total_counties": 47,
      "data_quality": "high"
    }

and holding SIX counties — Nairobi, Mombasa, Nakuru, Kiambu, Kisumu and Uasin
Gishu. Forty-seven is not a rounding of six. The file's own body contradicts
its own header, and no test in the repo could see it, because the three guards
this one sits beside all read Python and this is data.

That gap is the reason for a fourth rule. ``test_apis_no_invented_county_
rankings.py`` (#183), ``test_apis_no_invented_national_figures.py`` (#188) and
``test_no_published_figure_from_hash_or_clock.py`` (#193) parse ``*.py`` under
``apis/``, ``analysis/`` and ``extractors/``. Move the same claim from a dict
literal in a module into a ``.json`` beside it and every one of them goes
green.

TWO RULES, and they are separate claims.

RULE ONE — A DECLARED POPULATION MUST BE THE POPULATION HELD. A key of the
shape ``total_<things>``, ``<things>_count``, ``num_<things>``,
``number_of_<things>`` or ``count_of_<things>``, holding a non-negative
integer, is a declaration about how many of ``<thing>`` the document carries.
If the document holds a collection under a key that names the same thing, the
two must agree.

  THE NOUN MUST BE PLURAL, and that is not decoration. Dropped, this rule
  reads ``total_debt: 11500`` in ``frontend/e2e/fixtures/debt_overview.json``
  as a declaration of 11,500 debts, finds ``debt_breakdown`` holding four
  entries beside it, and reports a defect. It is a money total, not a census.
  ``total_counties`` counts counties; ``total_debt``, ``total_budget`` and
  ``total_expenditure`` count nothing. The singular/plural split separates them
  mechanically, with no list of financial words to keep current.
  ``test_a_money_total_is_not_a_population`` pins this.

RULE TWO — A FIXTURE MAY NOT NAME SOME-BUT-NOT-ALL COUNTIES AS BETTER OR WORSE
THAN THE REST. This is #183's rule, unchanged, applied to data. The same file
carries::

    "summary_insights": {
      "best_performing_county": "Uasin Gishu",
      "counties_needing_improvement": ["Mombasa", "Kisumu"]
    }

Three named county governments sorted into a good half and a bad half — over
six counties, presented as a fixture covering forty-seven. #187's docstring
gives the reason this is worth a rule and not a shrug: naming a public body as
one needing improvement is a statement of fact about it, actionable under the
Defamation Act (Cap 36), whether or not anything ordered the list.

The county roster and the judgement vocabulary are IMPORTED from #183's guard
rather than copied. Two rosters drift; one does not.

  A LIST AND A DICT ARE NOT THE SAME CLAIM. A list of county names is a
  selection whatever the key is called — that is #183's rule and it carries
  over unchanged. A dict KEYED by county is a data table, and this same file's
  ``county_data`` holds six of them; calling that a verdict would make every
  partially-loaded table a defamation risk and teach people to ignore the rule.
  Partial coverage is rule one's business, and only when the file declares a
  count it does not hold. A county-keyed table under a judgement-shaped key is
  a verdict again, and does fire.

WHAT THIS RULE DELIBERATELY DOES NOT DO. It does not look for one column
derived from another, and the reason is that the shape is legitimate in this
repo twice over:

* ``backend/seeding/real_data/debt_timeline.json`` — ``total`` equals
  ``external + domestic`` in 11 of its 13 rows. That is a disclosed identity in
  a debt table, not a second observation dressed as one.
* ``backend/seeding/real_data/national_debt.json`` — ``principal`` equals
  ``outstanding`` in 6 of its 13 rows and differs in the other 7. Both columns
  are independently sourced. A correlation rule would call ``outstanding``
  derived; it is not, and #188's docstring records what two sessions of
  arithmetic argument cost before anyone noticed the register had two amount
  columns.

Both files are inside the sweep below, and
``test_the_two_legitimate_registers_are_scanned_and_clean`` asserts they are
reached and that they draw nothing. A rule that could not survive those two
files was not worth writing.

ESCAPE HATCH. JSON carries no comments, so the suppression is a key. Put a
``"_guard_ok"`` object at the top of the document::

    "_guard_ok": {"total_counties": "declared scope; coverage tracked in #NNN"}

mapping the offending key to a written reason. An empty reason buys nothing,
exactly as in the three guards beside this one.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

import pytest

from test_apis_no_invented_county_rankings import (
    CANON_TO_COUNTY,
    JUDGEMENT_WORDS,
    _canonical,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# Where committed data lives. ``frontend/public/`` is left out on purpose: it
# holds county cartography (GeoJSON boundaries for all 47), which is reference
# geometry, not a claim about public money.
SCANNED_ROOTS = (
    REPO_ROOT / "apis",
    REPO_ROOT / "analysis",
    REPO_ROOT / "extractors",
    REPO_ROOT / "backend" / "seeding",
    REPO_ROOT / "backend" / "data",
)

SUPPRESSION_KEY = "_guard_ok"

# ``total_counties``, ``report_count``, ``num_rows``, ``number_of_findings``.
COUNT_KEY_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"^total_(?P<noun>.+)$",
        r"^(?P<noun>.+)_count$",
        r"^num_(?P<noun>.+)$",
        r"^number_of_(?P<noun>.+)$",
        r"^count_of_(?P<noun>.+)$",
    )
)

# Container suffixes that do not change what is being counted: ``county_data``
# holds counties.
CONTAINER_SUFFIXES = ("_data", "_list", "_records", "_entries", "_table", "_map")


def _is_plural(noun: str) -> bool:
    """True for ``counties``, ``reports``, ``rows``; false for ``debt``, ``budget``.

    Only the last word matters — ``pending_bills`` is plural, ``debt`` is not.
    A mass noun ending ``-ss`` (``progress``) is not a plural.
    """
    word = noun.lower().rsplit("_", 1)[-1]
    if word.endswith("ss"):
        return False
    return word.endswith("ies") or (word.endswith("s") and len(word) > 2)


def _stem(noun: str) -> str:
    """Fold ``counties``, ``county_data`` and ``county`` to one key."""
    stemmed = noun.lower()
    for suffix in CONTAINER_SUFFIXES:
        if stemmed.endswith(suffix):
            stemmed = stemmed[: -len(suffix)]
    if stemmed.endswith("ies"):
        return stemmed[:-3] + "y"
    if stemmed.endswith("s") and not stemmed.endswith("ss"):
        return stemmed[:-1]
    return stemmed


def _counted_noun(key: str) -> str | None:
    """The stemmed thing a key declares a count of, or None if it declares none."""
    for pattern in COUNT_KEY_PATTERNS:
        match = pattern.match(key.lower())
        if match:
            noun = match.group("noun")
            return _stem(noun) if _is_plural(noun) else None
    return None


def _walk(node: Any, path: str = "$") -> Iterator[tuple[str, str, Any]]:
    """Yield ``(path, key, value)`` for every key in the document."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path, key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{path}[{index}]")


def _collections_by_noun(node: Any, path: str = "$", out: dict | None = None) -> dict:
    """Every dict/list in the document, indexed by the stem of its key."""
    if out is None:
        out = {}
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                out.setdefault(_stem(key), []).append((f"{path}.{key}", len(value)))
                _collections_by_noun(value, f"{path}.{key}", out)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, (dict, list)):
                _collections_by_noun(value, f"{path}[{index}]", out)
    return out


def _suppressed(document: Any, key: str) -> bool:
    """True if a root ``_guard_ok`` entry WITH A REASON covers ``key``."""
    if not isinstance(document, dict):
        return False
    reasons = document.get(SUPPRESSION_KEY)
    if not isinstance(reasons, dict):
        return False
    reason = reasons.get(key)
    return isinstance(reason, str) and bool(reason.strip())


def _named_counties(value: Any) -> tuple[set[str], int]:
    """Canonical county names in a list of strings or a dict's keys, and its size."""
    if isinstance(value, list) and value and all(isinstance(e, str) for e in value):
        strings = value
    elif isinstance(value, dict) and value and all(isinstance(k, str) for k in value):
        strings = list(value)
    else:
        return set(), 0
    named = {
        CANON_TO_COUNTY[_canonical(s)] for s in strings if _canonical(s) in CANON_TO_COUNTY
    }
    return named, len(strings)


def find_fixture_defects(document: Any, where: str = "<fixture>") -> list[str]:
    """Every declared-count mismatch and county verdict in a parsed document.

    Returns human-readable descriptions, one per offending key. Empty list
    means clean. This is the detector; the tests below are thin wrappers around
    it — over the real tree, over the payload it was written for, and over the
    shapes that must stay legal.
    """
    findings: list[str] = []
    collections = _collections_by_noun(document)

    for path, key, value in _walk(document):
        if _suppressed(document, key):
            continue

        # RULE ONE — a declared population must be the population held.
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            noun = _counted_noun(key)
            candidates = collections.get(noun, []) if noun else []
            if candidates and value not in {size for _, size in candidates}:
                held = ", ".join(f"{p} holds {n}" for p, n in candidates)
                findings.append(
                    f"{where}: {path}.{key} declares {value} {noun}(s), but {held}. "
                    f"A header that disagrees with the body is not metadata, it "
                    f"is a claim nothing in the file supports."
                )

        # RULE TWO — no sorting named counties into a good half and a bad half.
        judgemental = any(word in key.lower() for word in JUDGEMENT_WORDS)
        named, size = _named_counties(value)
        subset = 2 <= len(named) < 47 and len(named) >= size / 2
        # A LIST of county names is a selection whatever it is called — #183's
        # rule, unchanged. A DICT keyed by county is a data table, and a table
        # covering six counties is a coverage question, which rule one answers
        # when the file declares a count. Only a table under a judgement-shaped
        # key is a verdict.
        if isinstance(value, dict) and not judgemental:
            subset = False
        if subset:
            findings.append(
                f"{where}: {path}.{key} names {len(named)} of the 47 counties "
                f"({', '.join(sorted(named))})"
                + (" under a judgement-shaped key" if judgemental else "")
                + ". Nothing in this file ordered them. Serve a measured "
                "ranking or serve nothing."
            )
        elif judgemental and isinstance(value, str) and _canonical(value) in CANON_TO_COUNTY:
            findings.append(
                f"{where}: {path}.{key} = {value!r}, a single named county under "
                f"a judgement-shaped key. That is a statement of fact about a "
                f"public body; measure it or withdraw it."
            )

    return findings


def _fixtures(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.json")) if root.is_dir() else []


SCANNED_FIXTURES = [f for root in SCANNED_ROOTS for f in _fixtures(root)]


def _rel(fixture: Path) -> str:
    return fixture.relative_to(REPO_ROOT).as_posix()


def _load(fixture: Path) -> Any | None:
    """The parsed document, or None for an empty or unparsable file.

    ``etl_check.json`` and ``seeder_status.json`` are committed at zero bytes.
    A malformed fixture is a real problem, but it is not THIS rule's problem,
    and going red on it would make this guard say something it did not check.
    """
    text = fixture.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


LEGITIMATE_REGISTERS = (
    "backend/seeding/real_data/debt_timeline.json",
    "backend/seeding/real_data/national_debt.json",
)


def test_the_scanned_roots_are_where_we_think_they_are():
    """Anti-vacuity: an empty sweep must never read as a pass.

    Skip if every root has been removed — deleting them is a legitimate outcome
    and the owner's call — but never let an empty or unparsable sweep read as a
    pass.

    Deliberately NOT asserted per root: ``analysis/`` holds no ``.json`` today
    and is scanned anyway, so that a fixture dropped there later is covered. A
    root holding no JSON is not a defect; a sweep that collected nothing, or
    parsed nothing, is. ``test_the_two_legitimate_registers_are_scanned_and_
    clean`` pins two real files by name, which is the stronger check.
    """
    surviving = [root for root in SCANNED_ROOTS if root.is_dir()]
    if not surviving:
        pytest.skip("every scanned root has been removed — nothing to guard")
    assert SCANNED_FIXTURES, "no fixtures collected — the sweep would be silent"
    parsed = [f for f in SCANNED_FIXTURES if _load(f) is not None]
    assert parsed, "every fixture failed to parse — the sweep read nothing"


def test_the_detector_catches_the_payload_it_was_written_for():
    """Positive control. Proves a green run below means clean, not blind.

    This is the header and the summary block of
    ``apis/enhanced_cob_extraction_results.json`` as issue #196 found them.
    """
    known_bad = {
        "extraction_metadata": {
            "source": "Controller of Budget Reports",
            "total_counties": 47,
            "data_quality": "high",
        },
        "local_pdf_data": {
            "county_data": {
                "Nairobi": {},
                "Mombasa": {},
                "Nakuru": {},
                "Kiambu": {},
                "Kisumu": {},
                "Uasin Gishu": {},
            }
        },
        "summary_insights": {
            "best_performing_county": "Uasin Gishu",
            "counties_needing_improvement": ["Mombasa", "Kisumu"],
        },
    }
    findings = find_fixture_defects(known_bad, "known_bad.json")
    blob = "\n".join(findings)

    assert "declares 47 county(s)" in blob, f"the 47-vs-6 header slipped through: {findings}"
    assert "holds 6" in blob, f"the finding did not name what the body holds: {findings}"
    assert "best_performing_county" in blob, f"the single-county verdict slipped through: {findings}"
    assert "counties_needing_improvement" in blob, f"the two-county verdict slipped through: {findings}"
    assert len(findings) == 3, f"expected exactly three findings, got: {findings}"

    # Renaming the verdict keys must not get past rule two — the subset IS the
    # claim, exactly as in #183's guard.
    renamed = json.loads(
        json.dumps(known_bad)
        .replace("counties_needing_improvement", "group_b")
        .replace("best_performing_county", "group_a")
    )
    renamed_findings = find_fixture_defects(renamed, "renamed.json")
    assert any("group_b" in f for f in renamed_findings), (
        f"renaming the key defeated the subset rule: {renamed_findings}"
    )

    # Rule one does not care what the count is called, only that it disagrees.
    for key in ("total_counties", "counties_count", "num_counties", "number_of_counties"):
        variant = {"meta": {key: 47}, "county_data": {"Nairobi": {}, "Kisumu": {}}}
        assert find_fixture_defects(variant, "variant.json"), (
            f"a count declared as {key!r} was not read as a declaration"
        )

    # An empty suppression buys nothing.
    unreasoned = dict(known_bad, _guard_ok={"total_counties": "   "})
    assert any("total_counties" in f for f in find_fixture_defects(unreasoned, "u.json")), (
        "an empty suppression bought silence for free"
    )


def test_a_money_total_is_not_a_population():
    """Negative control for the singular/plural split, and it is load-bearing.

    Without it, this shape — which is real, in
    ``frontend/e2e/fixtures/debt_overview.json`` — reads as a declaration of
    11,500 debts contradicted by four ``debt_breakdown`` entries. It is a money
    total in billions.
    """
    money = {
        "data": {
            "total_debt": 11500,
            "debt_breakdown": {
                "external": 5300,
                "domestic": 6200,
                "multilateral": 2100,
                "bilateral": 1400,
            },
        }
    }
    assert not find_fixture_defects(money, "money.json"), find_fixture_defects(
        money, "money.json"
    )

    for singular, container in (
        ("total_budget", "budget_lines"),
        ("total_expenditure", "expenditure_items"),
        ("total_revenue", "revenue_streams"),
    ):
        doc = {singular: 987_654_321, container: [1, 2, 3]}
        assert not find_fixture_defects(doc, "s.json"), (
            f"{singular!r} was read as a population count"
        )

    # ... and a genuine population declaration still fires.
    assert find_fixture_defects(
        {"total_reports": 9, "reports": [1, 2, 3]}, "p.json"
    ), "a plural count that disagrees with its collection must fire"


def test_the_detector_leaves_reference_data_and_agreeing_counts_alone():
    """Negative control. A full roster and an honest count must stay legal."""
    full_roster = {
        "counties": sorted(CANON_TO_COUNTY.values()),
        "total_counties": 47,
    }
    assert not find_fixture_defects(full_roster, "roster.json"), find_fixture_defects(
        full_roster, "roster.json"
    )

    agreeing = {"metadata": {"total_rows": 2}, "rows": [{"a": 1}, {"a": 2}]}
    assert not find_fixture_defects(agreeing, "agree.json"), find_fixture_defects(
        agreeing, "agree.json"
    )

    # A county-keyed data table under a neutral key is coverage, not a verdict:
    # rule one is what catches partial coverage, and only when it is declared.
    table = {"county_data": {"Nairobi": {"budget": 1}, "Kisumu": {"budget": 2}}}
    assert not find_fixture_defects(table, "table.json"), find_fixture_defects(
        table, "table.json"
    )

    # ... but the SAME table under a judgement-shaped key is a verdict, and a
    # bare LIST of county names is one whatever it is called (#183's rule).
    assert find_fixture_defects(
        {"top_counties": {"Nairobi": {}, "Kisumu": {}}}, "verdict.json"
    ), "a county table under a judgement-shaped key must fire"
    assert find_fixture_defects({"group_a": ["Nairobi", "Kisumu"]}, "list.json"), (
        "a bare list of county names must fire whatever the key is called"
    )

    # A suppression with a written reason is honoured.
    signed = {
        "_guard_ok": {"total_counties": "declared national scope; six loaded so far"},
        "total_counties": 47,
        "county_data": {"Nairobi": {}},
    }
    assert not find_fixture_defects(signed, "signed.json"), (
        "a suppression with a written reason must be honoured"
    )


def test_the_two_legitimate_registers_are_scanned_and_clean():
    """The rule must survive the two files a derivation rule would have broken.

    Not a synthetic control: these are the real registers, read off disk, and
    the assertion is that the sweep REACHES them and that they draw nothing.
    """
    scanned = {_rel(f) for f in SCANNED_FIXTURES}
    for register in LEGITIMATE_REGISTERS:
        path = REPO_ROOT / register
        if not path.is_file():
            pytest.skip(f"{register} has been removed")
        assert register in scanned, (
            f"{register} is not inside the sweep — this control proves nothing"
        )
        document = _load(path)
        assert document is not None, f"{register} did not parse"
        assert not find_fixture_defects(document, register), find_fixture_defects(
            document, register
        )


@pytest.mark.skipif(not SCANNED_FIXTURES, reason="the scanned roots hold no fixtures")
@pytest.mark.parametrize(
    "fixture",
    SCANNED_FIXTURES,
    ids=[_rel(f) for f in SCANNED_FIXTURES] or ["none"],
)
def test_no_fixture_declares_more_than_it_holds(fixture: Path):
    document = _load(fixture)
    if document is None:
        pytest.skip(f"{_rel(fixture)} is empty or does not parse as JSON")
    findings = find_fixture_defects(document, _rel(fixture))
    assert not findings, "\n".join(
        ["committed fixture claims nothing in it supports:", *findings]
    )
