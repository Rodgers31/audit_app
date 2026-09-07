"""No service under ``apis/`` may hand-pick a list of named counties.

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

THE RULE. A module under ``apis/`` may not contain a literal list of strings
that names some-but-not-all of Kenya's 47 counties. A hand-typed subset IS the
judgement — which counties made the list is the claim, and no amount of
renaming the key changes that. The full 47 are exempt: a complete roster is a
reference table, not a selection.

Renaming ``best_performing_counties`` to ``group_a`` therefore does not get you
past this. A single county under a judgement-flavoured key does not either.

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
APIS_DIR = REPO_ROOT / "apis"

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


def find_county_selections(source: str, where: str = "<source>") -> list[str]:
    """Every hand-picked list of named counties in ``source``.

    Returns human-readable descriptions, one per offending literal. Empty list
    means clean. This is the detector; the tests below are two thin wrappers
    around it, one over the real tree and one over a known-bad string.
    """
    tree = ast.parse(source, filename=where)
    labels = _labels(tree)
    lines = source.splitlines()
    findings: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            continue
        elements = node.elts
        if not elements:
            continue
        strings = [
            e.value for e in elements
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]
        if len(strings) != len(elements):
            continue  # not a pure literal — a comprehension or computed list

        named = {
            CANON_TO_COUNTY[_canonical(s)]
            for s in strings
            if _canonical(s) in CANON_TO_COUNTY
        }
        if not named:
            continue

        label = labels.get(id(node), "")
        judgemental = any(word in label.lower() for word in JUDGEMENT_WORDS)

        # (a) A subset of the 47, mostly counties: the selection IS the claim.
        subset = (
            len(named) >= 2
            and len(named) < 47
            and len(named) >= len(strings) / 2
        )
        # (b) A single county under a verdict-shaped key.
        verdict = judgemental and len(named) >= 1

        if not (subset or verdict):
            continue
        if _suppressed(lines, node):
            continue

        findings.append(
            f"{where}:{node.lineno}: "
            + (f"{label!r} is " if label else "an unnamed literal is ")
            + f"a hand-picked list of {len(named)} of the 47 counties "
            + f"({', '.join(sorted(named))})"
            + (" under a judgement-shaped key" if judgemental else "")
            + ". Nothing ordered it. Serve a measured ranking or serve nothing."
        )

    return findings


API_MODULES = sorted(APIS_DIR.glob("*.py")) if APIS_DIR.is_dir() else []


def test_the_apis_directory_is_where_we_think_it_is():
    """Anti-vacuity: if apis/ has no modules, every check below is silent.

    Skip rather than fail if the whole directory is gone — deleting it is a
    legitimate outcome — but never let an empty scan read as a pass.
    """
    if not APIS_DIR.is_dir():
        pytest.skip("apis/ has been removed entirely — nothing to guard")
    assert API_MODULES, "apis/ exists but holds no .py files — scan would be vacuous"


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


@pytest.mark.skipif(not API_MODULES, reason="apis/ has no modules")
@pytest.mark.parametrize(
    "module",
    API_MODULES,
    ids=[m.name for m in API_MODULES] or ["none"],
)
def test_no_api_module_hand_picks_named_counties(module: Path):
    findings = find_county_selections(
        module.read_text(encoding="utf-8"), f"apis/{module.name}"
    )
    assert not findings, "\n".join(["hand-picked county lists found:", *findings])
