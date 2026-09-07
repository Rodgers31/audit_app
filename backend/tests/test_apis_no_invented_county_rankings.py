"""No module under ``apis/``, ``analysis/`` or ``extractors/`` may hand-pick a
set of named counties.

On 2026-09-07, ``apis/enhanced_county_analytics_api.py`` served this from
``GET /analytics/comprehensive``::

    "best_performing_counties": ["Nairobi", "Kiambu", "Mombasa", "Nakuru",
                                 "Uasin Gishu"],
    "improvement_needed": ["Mandera", "Wajir", "Garissa", "Tana River", "Lamu"],

Ten named county governments, sorted into a good half and a bad half by
nothing. No execution rate was compared, no audit finding counted, no query
run — the two lists are literals someone typed. Beside them sat
``total_irregular_expenditure: 24_700_000_000``, a measure of a quantity the
pipeline does not classify at all.

PR #182 had just withdrawn the same defect in its weaker form (``worst_counties``,
which at least ordered *something*) from the shipping backend. This was the
stronger form, and it survived only because the service was not wired up.

That is the reason for a guard rather than a fix. A payload nothing calls today
is one launcher entry away from a reader, and the harm here does not need a
reader to be real in principle: naming Mandera, Wajir, Garissa, Tana River and
Lamu as the counties needing improvement is a statement of fact about five
public bodies, actionable under the Defamation Act (Cap 36) whether or not the
number beside it is flattering.

THE RULE. A module under one of the scanned roots may not contain a literal
that names some-but-not-all of Kenya's 47 counties. A hand-typed subset IS the
judgement — which counties made the list is the claim, and no amount of
renaming the key changes that. The full 47 are exempt: a complete roster is a
reference table, not a selection.

Renaming ``best_performing_counties`` to ``group_a`` therefore does not get you
past this. A single county under a judgement-flavoured key does not either.

TWO SHAPES, AND WHY THE SECOND WAS ADDED (issue #198). The original rule read
list literals only. ``extractors/county/enhanced_county_extractor.py:210-260``
wrote the same claim as a *mapping*::

    county_profiles = {
        "Nairobi City": {"audit_rating": "B+", "missing_funds": 2100000000,
                         "major_issues": ["Delayed project implementation ...
        "Mombasa":      {"audit_rating": "B",  "missing_funds": 890000000, ...
        "Kiambu":       {"audit_rating": "A-", "missing_funds": 420000000, ...
        "Nakuru":       {"audit_rating": "B+", "missing_funds": 680000000, ...
    }

Four of the 47 singled out, each given a grade no auditor issued, a
missing-public-money figure nobody measured, and a named failing. Turning the
list on its side does not make it reference data, so a county-keyed dict whose
values are RECORDS — dicts, lists, tuples, sets — reads the same as a list.

A county-keyed dict of SCALARS does not, and that distinction is load-bearing
rather than convenient. ``official_county_budget_extractor.py:414``'s
``economic_factors`` maps seven counties to a float and is read with
``.get(county, 1.0)``, so every county gets a value and the seven names are
parameters, not a selection. A per-county record says something *about* that
county; a coefficient says something about the formula.

WHY THE ROOTS GREW. This guard was rooted at ``apis/`` because that is where
the payload it was written for sat. ``extractors/`` ships — ``Dockerfile:26``
copies it into the production image — and the two guards beside this file
(``test_apis_no_invented_national_figures.py``,
``test_no_published_figure_from_hash_or_clock.py``) already scan all three
roots. A claim about a named county government is the same claim whichever
directory it is typed in.

ESCAPE HATCH, following ``local/no-zero-fallback-on-published-figure`` (7b5d366):
a suppression must carry a written reason. Put

    # counties-literal-ok: <why this subset is not a judgement>

on the line the literal opens, or the line above it. The reason is the point —
it makes a hand-picked list something a person signed for.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_ROOTS = (
    REPO_ROOT / "apis",
    REPO_ROOT / "analysis",
    REPO_ROOT / "extractors",
)

# The 47 counties of the First Schedule to the Constitution of Kenya (2010).
# Hardcoded deliberately: this guard must not weaken because a roster file
# somewhere else moved or shrank.
COUNTIES_47 = [
    "Mombasa", "Kwale", "Kilifi", "Tana River", "Lamu", "Taita-Taveta",
    "Garissa", "Wajir", "Mandera", "Marsabit", "Isiolo", "Meru",
    "Tharaka-Nithi", "Embu", "Kitui", "Machakos", "Makueni", "Nyandarua",
    "Nyeri", "Kirinyaga", "Murang'a", "Kiambu", "Turkana", "West Pokot",
    "Samburu", "Trans-Nzoia", "Uasin Gishu", "Elgeyo-Marakwet", "Nandi",
    "Baringo", "Laikipia", "Nakuru", "Narok", "Kajiado", "Kericho", "Bomet",
    "Kakamega", "Vihiga", "Bungoma", "Busia", "Siaya", "Kisumu", "Homa Bay",
    "Migori", "Kisii", "Nyamira", "Nairobi",
]
assert len(COUNTIES_47) == 47, "the county roster is wrong — this guard is broken"

# Words that turn a list of counties into a verdict about them. Used only to
# catch the single-county case; the subset rule below does not need them.
JUDGEMENT_WORDS = (
    "best", "worst", "top", "bottom", "rank", "perform", "improve",
    "improvement", "lead", "lag", "poor", "good", "fail", "success", "most",
    "least", "highest", "lowest", "flag", "problem", "corrupt", "mismanag",
    "risk", "offend", "culprit", "winner", "loser", "excellent", "weak",
    "strong", "worse", "better", "priority", "concern",
)

SUPPRESSION = "counties-literal-ok:"


def _canonical(text: str) -> str:
    """Fold a county name to a comparable key.

    Handles the spellings the repo already normalises elsewhere: a trailing
    " County", curly apostrophes, and hyphen/space variance in the compound
    names (Taita-Taveta, Trans-Nzoia, Elgeyo-Marakwet, Tharaka-Nithi).
    """
    key = text.strip().lower().replace("’", "'")
    if key.endswith(" county"):
        key = key[: -len(" county")]
    return key.replace("-", " ").replace("'", "").replace("  ", " ").strip()


CANON_TO_COUNTY = {_canonical(name): name for name in COUNTIES_47}
assert len(CANON_TO_COUNTY) == 47, "county canonicalisation collided"


def _labels(tree: ast.AST) -> dict[int, str]:
    """Map each literal node to the name it is published under, if any."""
    labels: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    labels[id(value)] = key.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    labels[id(node.value)] = target.id
                elif isinstance(target, ast.Attribute):
                    labels[id(node.value)] = target.attr
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                labels[id(node.value)] = node.target.id
        elif isinstance(node, ast.keyword) and node.arg:
            labels[id(node.value)] = node.arg
    return labels


def _suppressed(source_lines: list[str], node: ast.AST) -> bool:
    """True if a ``counties-literal-ok:`` comment WITH A REASON covers node."""
    start = max(1, getattr(node, "lineno", 1) - 1)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    for lineno in range(start, end + 1):
        line = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
        if SUPPRESSION in line:
            reason = line.split(SUPPRESSION, 1)[1].strip()
            if reason:
                return True
    return False


def _county_names(strings: list[str]) -> set[str]:
    """The canonical counties among ``strings``."""
    return {
        CANON_TO_COUNTY[_canonical(s)]
        for s in strings
        if _canonical(s) in CANON_TO_COUNTY
    }


def _is_a_selection(named: set[str], total: int, judgemental: bool) -> bool:
    """Is this set of names a hand-picked subset, or a verdict on one county?

    (a) two or more of the 47, but not all 47, and mostly counties: the
        selection IS the claim; or
    (b) a single county under a verdict-shaped key.
    """
    subset = 2 <= len(named) < 47 and len(named) >= total / 2
    return subset or (judgemental and len(named) >= 1)


def find_county_selections(source: str, where: str = "<source>") -> list[str]:
    """Every hand-picked set of named counties in ``source``.

    Two shapes, both described in the module docstring: a list/tuple/set of
    county-name strings, and a dict keyed by county names whose values are
    RECORDS. Returns human-readable descriptions, one per offending literal.
    Empty list means clean. This is the detector; the tests below are thin
    wrappers around it, over the real tree and over known-bad strings.
    """
    tree = ast.parse(source, filename=where)
    labels = _labels(tree)
    lines = source.splitlines()
    findings: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            elements = node.elts
            if not elements:
                continue
            strings = [
                e.value for e in elements
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
            if len(strings) != len(elements):
                continue  # not a pure literal — a comprehension or computed list
            shape = "list"
        elif isinstance(node, ast.Dict):
            pairs = [
                (key.value, value)
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            # ``{**base, "Nairobi": {...}}`` has a None key; a computed key is
            # not a literal either. Either way this is not a hand-typed table.
            if not pairs or len(pairs) != len(node.keys):
                continue
            # Only a dict of RECORDS. A county-keyed dict of scalars is a
            # coefficient table read with .get(county, default), which gives
            # every county a value — see the module docstring.
            if not all(
                isinstance(value, (ast.Dict, ast.List, ast.Tuple, ast.Set))
                for _, value in pairs
            ):
                continue
            strings = [key for key, _ in pairs]
            shape = "mapping"
        else:
            continue

        named = _county_names(strings)
        if not named:
            continue

        label = labels.get(id(node), "")
        judgemental = any(word in label.lower() for word in JUDGEMENT_WORDS)
        if not _is_a_selection(named, len(strings), judgemental):
            continue
        if _suppressed(lines, node):
            continue

        findings.append(
            f"{where}:{node.lineno}: "
            + (f"{label!r} is " if label else "an unnamed literal is ")
            + (
                f"a hand-picked list of {len(named)} of the 47 counties "
                if shape == "list"
                else f"a hand-typed record for {len(named)} of the 47 counties "
            )
            + f"({', '.join(sorted(named))})"
            + (" under a judgement-shaped key" if judgemental else "")
            + ". Nothing ordered it. Serve a measured ranking or serve nothing."
        )

    return findings


def _modules(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py")) if root.is_dir() else []


SCANNED_MODULES = [m for root in SCANNED_ROOTS for m in _modules(root)]


def _rel(module: Path) -> str:
    return module.relative_to(REPO_ROOT).as_posix()


def test_the_scanned_directories_are_where_we_think_they_are():
    """Anti-vacuity: an empty sweep must never read as a pass.

    Skip a root that has been removed entirely — deleting one is a legitimate
    outcome and the owner's call — but fail if a root exists and the scan finds
    nothing in it, and fail if every root has vanished at once.
    """
    surviving = [root for root in SCANNED_ROOTS if root.is_dir()]
    if not surviving:
        pytest.skip("every scanned root has been removed — nothing to guard")
    for root in surviving:
        assert _modules(root), (
            f"{root.name}/ exists but holds no .py files — its scan would be vacuous"
        )
    assert SCANNED_MODULES, "no modules collected — the sweep would be silent"


def test_the_detector_catches_the_payload_it_was_written_for():
    """Positive control. Proves a green run below means clean, not blind.

    This is the exact block deleted from
    ``apis/enhanced_county_analytics_api.py:993-1000``. If the detector ever
    stops flagging it, the scan over the real tree is worthless and this test
    says so.
    """
    known_bad = '''
payload = {
    "performance_comparison": {
        "best_performing_counties": [
            "Nairobi", "Kiambu", "Mombasa", "Nakuru", "Uasin Gishu",
        ],
        "improvement_needed": ["Mandera", "Wajir", "Garissa", "Tana River", "Lamu"],
    },
}
'''
    findings = find_county_selections(known_bad, "known_bad.py")
    assert len(findings) == 2, f"detector missed the defect it exists for: {findings}"
    assert any("best_performing_counties" in f for f in findings)
    assert any("improvement_needed" in f for f in findings)

    # Renaming the key must not get past it — the subset is the judgement.
    renamed = known_bad.replace("best_performing_counties", "group_a").replace(
        "improvement_needed", "group_b"
    )
    assert len(find_county_selections(renamed, "renamed.py")) == 2, (
        "the guard keys on the label alone — a rename would defeat it"
    )

    # A single county under a verdict-shaped key must also fail.
    single = 'payload = {"worst_county": ["Mandera"]}'
    assert find_county_selections(single, "single.py"), (
        "a one-county verdict slipped through"
    )


def test_the_detector_catches_the_mapping_shape_too():
    """Positive control for the second shape, added by issue #198.

    This is the block withdrawn from
    ``extractors/county/enhanced_county_extractor.py:210-260`` — four counties
    out of 47, each handed a grade, a missing-public-money figure and a named
    failing, none of it extracted from anything.
    """
    known_bad = '''
county_profiles = {
    "Nairobi City": {
        "budget_2025": 37500000000,
        "audit_rating": "B+",
        "missing_funds": 2100000000,
        "major_issues": ["Delayed project implementation (30% of budget)"],
    },
    "Mombasa": {
        "budget_2025": 18000000000,
        "audit_rating": "B",
        "missing_funds": 890000000,
        "major_issues": ["Port revenue sharing disputes"],
    },
    "Kiambu": {"audit_rating": "A-", "missing_funds": 420000000},
    "Nakuru": {"audit_rating": "B+", "missing_funds": 680000000},
}
'''
    findings = find_county_selections(known_bad, "known_bad.py")
    assert len(findings) == 1, f"the mapping shape slipped through: {findings}"
    assert "county_profiles" in findings[0]
    assert "hand-typed record" in findings[0], findings

    # Renaming the binding must not help — the selection is the claim.
    renamed = known_bad.replace("county_profiles", "table_a")
    assert len(find_county_selections(renamed, "renamed.py")) == 1, (
        "the guard keys on the label alone — a rename would defeat it"
    )

    # A written reason buys silence; an empty one does not.
    signed = known_bad.replace(
        "county_profiles = {",
        "county_profiles = {  # counties-literal-ok: transcribed from OAG p.14",
    )
    assert not find_county_selections(signed, "signed.py"), (
        "a suppression with a written reason must be honoured"
    )
    unreasoned = known_bad.replace(
        "county_profiles = {", "county_profiles = {  # counties-literal-ok:"
    )
    assert find_county_selections(unreasoned, "unreasoned.py"), (
        "an empty suppression bought silence for free"
    )


def test_the_detector_does_not_flag_a_full_roster_or_a_lookup():
    """Negative control. A complete roster is reference data, not a selection."""
    roster = "COUNTY_NAMES = [\n" + "".join(
        f'    "{name}",\n' for name in COUNTIES_47
    ) + "]\n"
    assert not find_county_selections(roster, "roster.py"), (
        "the full 47 are a reference table and must not trip the guard"
    )

    assert not find_county_selections(
        'STATUSES = ["draft", "published", "withdrawn"]', "statuses.py"
    )

    # A complete county-keyed table of records is reference data too.
    full_map = "COUNTY_META = {\n" + "".join(
        f'    "{name}": {{"code": "{i:03d}"}},\n'
        for i, name in enumerate(COUNTIES_47, start=1)
    ) + "}\n"
    assert not find_county_selections(full_map, "full_map.py"), (
        "a complete county-keyed table must not trip the guard"
    )

    # A county-keyed dict of SCALARS is a coefficient table, not a selection.
    # This is ``official_county_budget_extractor.py:414`` in miniature: read
    # with ``.get(county, 1.0)``, so every county gets a value.
    coefficients = '''
economic_factors = {"Nairobi": 2.5, "Mombasa": 1.8, "Nakuru": 1.4, "Kiambu": 1.3}
factor = economic_factors.get(county, 1.0)
'''
    assert not find_county_selections(coefficients, "coefficients.py"), (
        "a per-county coefficient read with a default is a parameter, not a "
        "claim about the counties named"
    )


@pytest.mark.skipif(not SCANNED_MODULES, reason="the scanned roots hold no modules")
@pytest.mark.parametrize(
    "module",
    SCANNED_MODULES,
    ids=[_rel(m) for m in SCANNED_MODULES] or ["none"],
)
def test_no_module_hand_picks_named_counties(module: Path):
    findings = find_county_selections(
        module.read_text(encoding="utf-8"), _rel(module)
    )
    assert not findings, "\n".join(["hand-picked county selections found:", *findings])
