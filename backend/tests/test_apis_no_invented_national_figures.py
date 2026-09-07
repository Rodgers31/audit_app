"""No module under ``apis/``, ``analysis/`` or ``extractors/`` may type in a
public-finance figure.

On 2026-09-07, ``apis/data_driven_analytics.py`` — and its byte-identical twin
``analysis/data_driven_analytics.py`` (md5 ``e0713a40054986c9c0ca51d99c4f406c``)
— opened with the claim that it "reads from actual extracted data files instead
of hard-coded values", and then returned this::

    current_debt = {
        "total_debt": 11500000000000,       # 11.5T KES (verified online)
        "verification_status": "manually_verified",
    }
    external_percentage = 60.0              # Typical for Kenya
    "debt_to_gdp_ratio": 70.2,              # Updated calculation

    def _calculate_debt_trend(self) -> Dict[str, int]:
        return {"2020": 7400000000000, "2021": 8200000000000,
                "2022": 9100000000000, "2023": 10200000000000,
                "2024": 11500000000000}

A function called ``_calculate_debt_trend`` that calculates nothing, five typed
constants, and a split that is ``total * 0.6`` / ``total * 0.4``. Every point of
that series disagrees with ``backend/seeding/real_data/debt_timeline.json``,
which carries CBK figures cited to the PDF page — including the sign of the
2023→2024 move, which CBK records as a *fall* (11,139.7 → 10,925.3 Bn) and the
module drew as a rise. The 60% external share is on the wrong side of the
majority: CBK puts 2024 external at 46.3%, and the repo's own loan register at
47.4% on outstanding (5,276 of 11,140 Bn) or 47.6% on principal (5,326 of
11,190 Bn), summing all 13 rows of ``national_debt.json`` both ways. Read one
column while quoting the other and the difference looks like an addition slip;
the register carries both, and they differ on 7 of its 13 rows — rows 1, 2, 3,
5, 6, 7 and 8. (This said 8 until issue #193 recounted it. Row 4,
``Multilateral (Other — EIB, IFAD, IFC)``, is 95.0 Bn in both columns and was
counted as differing. The totals and shares above are unaffected and were
right.)
``outstanding`` is the basis the repo publishes on — ``backend/main.py:369``,
``:492``, ``:2462``, ``:4428`` and ``test_debt_total_double_count.py:117`` all
sum ``outstanding``, falling back to ``principal`` only where it is absent —
and it is the like-for-like comparator, CBK's figure being a stock outstanding.
The choice does not matter to the point: both are below half, and the module
said 60%.

Beside them, ministry "execution rates" were ``abs(hash(ministry)) % 25``
arithmetic, labelled ``"data_derivation": "calculated_from_actual_budget_data"``
— a number that changes on every server restart, because ``hash()`` on a ``str``
is salted per process.

NOTE FOR ANYONE TEMPTED TO TEST THE INSTABILITY DIRECTLY: do not. This guard
keys on the literal in the source, which is seed-independent, and the rule
about ``hash()`` itself now lives in
``test_no_published_figure_from_hash_or_clock.py`` (issue #193). The reason is
that ``hash()`` is stable *within* a process whatever the seed, so a
run-it-twice test in one interpreter finds these values rock steady even while
the defect is live, and a runner that pinned ``PYTHONHASHSEED`` would freeze
them across processes too. (This note previously said pytest pins that variable.
It does not here — ``pytest-randomly`` is not installed and
``os.environ.get("PYTHONHASHSEED")`` is ``None`` under this runner. The
conclusion was right for the weaker reason.)

THE RULE. A module under ``apis/``, ``analysis/`` or ``extractors/`` may not
publish a numeric literal under a name that denotes a measured public-finance quantity — a debt,
a budget, a revenue, an allocation, a ratio, a rate, a share, a score. If the
figure is measured, it comes from the data; if it is typed, it is invented. This
holds however the literal is dressed: bare (``"total_debt": 11500000000000``),
arithmetic on typed factors (``revenue_target = national_budget * 0.75``), or
buried in a clamp (``min(95, max(60, 75 + (h % 25) - 12))``) — the whole value
expression is scanned, because #178/#179 were exactly the case where published
figures turned out to be arithmetic rather than measurement.

Separately, a dict mapping four-digit years to numbers is a hand-typed time
series and is barred on its own, whatever key it hangs under. That is the shape
``_calculate_debt_trend`` used, and no key name was involved.

``apis/`` AND ``analysis/`` ARE BOTH SCANNED, deliberately. The two copies are byte-identical;
a guard over ``apis/`` alone would go green on cleaning one of them while the
invented debt series stayed in the repo under ``analysis/``.

NOTE WHAT THIS GUARD IS AND IS NOT ASSERTING. Both modules still exist and are
still scanned — six methods were removed from them, not the files. So a green
run here means the surviving code is clean, not that the code went away. That
is the point: a test that a path does not exist pins the symptom, and this one
keeps biting on the pattern wherever it reappears.

WHAT IS NOT A FIGURE, and why each exemption is safe:

* ``0`` and ``0.0`` — an absence or an accumulator seed, not an invented
  measurement. The zero case has its own rule already:
  ``local/no-zero-fallback-on-published-figure`` (7b5d366).
* ``1`` and ``100`` — an identity and a percentage base.
* exact powers of ten from 1000 up — unit conversion (``/ 1_000_000_000`` to
  billions). 11500000000000 is not one; 1000000000 is.
* slice bounds (``rankings[:5]``) and the ``ndigits`` of ``round(x, 2)`` — list
  length and display precision are structure, not quantity.

EXTENDED TO ``extractors/`` 2026-09-07 (issue #193), and that root is the one
that matters. ``apis/`` and ``analysis/`` do not ship; ``Dockerfile:26`` does
``COPY extractors/ /app/extractors/``, so everything this sweep now reads is in
the production image. It caught 21 figures in
``extractors/government/comprehensive_government_extractor.py`` — a national
database typed in whole, including a debt block repeating #188's defects
independently (10.2T, 67.8% of GDP, a 59.8% external share) and a
``transparency_score: 95`` sitting in the same dict as genuinely counted
reports, unable to disagree with them.

A NUMBER THAT LOOKS THE SAME AND IS NOT.
``extractors/county/official_county_budget_extractor.py:45+`` holds 55 numeric
literals in a dict of named counties and is REFERENCE DATA — KNBS 2019 census
populations with official county codes. It draws no findings here, and the
reason is worth keeping: the rule fires on a literal under a label that names a
measured public-finance quantity, and ``population`` and ``code`` are neither.
Do not add ``population`` to ``SUBJECTS`` to make the sweep feel thorough; it
would turn a census into a defect. What separates it from the figures above is
not the shape of the literal but whether anybody measured it, and the census
was measured.

ESCAPE HATCH, following ``local/no-zero-fallback-on-published-figure``
(7b5d366) and the county guard beside this file: a suppression must carry a
written reason. Put

    # figure-literal-ok: <where this number comes from>

on the line the value opens, or the line above it. The reason is the point — a
figure with a source is not invented, and writing the source down is the whole
difference.
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

# A label names a measured public-finance quantity if it mentions what the
# figure is ABOUT ...
SUBJECTS = (
    "debt",
    "budget",
    "revenue",
    "expenditure",
    "allocation",
    "gdp",
    "deficit",
    "surplus",
    "funds",
    "disbursement",
    "arrears",
    "tax",
    "borrowing",
    "repayment",
    "transfers",
)
# ... or HOW it was measured.
MEASURES = (
    "execution_rate",
    "collection_rate",
    "performance_score",
    "transparency_score",
    "percentage",
    "_ratio",
    "_share",
)

EXEMPT_VALUES = {0, 1, 100}

SUPPRESSION = "figure-literal-ok:"


def _is_unit_conversion(value: int | float) -> bool:
    """True for an exact power of ten from 1000 up (``/ 1_000_000_000``)."""
    if not isinstance(value, int) or value < 1000:
        return False
    digits = str(value)
    return digits[0] == "1" and set(digits[1:]) <= {"0"}


def _is_figure(value: object) -> bool:
    """True if this literal is a quantity someone could have measured."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if value in EXEMPT_VALUES:
        return False
    return not _is_unit_conversion(value)


def _names_a_measured_quantity(label: str) -> bool:
    lowered = label.lower()
    return any(t in lowered for t in SUBJECTS) or any(t in lowered for t in MEASURES)


def _structural_literals(tree: ast.AST) -> set[int]:
    """Literal nodes that carry structure, not quantity.

    Slice bounds say how long a list is. ``round(x, 2)`` says how it is
    printed. Neither asserts anything about public money.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Slice):
            for part in (node.lower, node.upper, node.step):
                if part is not None:
                    ids.update(id(n) for n in ast.walk(part))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "round"
        ):
            for arg in node.args[1:]:
                ids.update(id(n) for n in ast.walk(arg))
            for kw in node.keywords:
                if kw.arg == "ndigits":
                    ids.update(id(n) for n in ast.walk(kw.value))
    return ids


def _labelled_values(tree: ast.AST) -> list[tuple[str, ast.AST]]:
    """Every value in the module paired with the name it is published under."""
    pairs: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    pairs.append((key.value, value))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    pairs.append((target.id, node.value))
                elif isinstance(target, ast.Attribute):
                    pairs.append((target.attr, node.value))
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            if isinstance(node.target, ast.Name):
                pairs.append((node.target.id, node.value))
        elif isinstance(node, ast.keyword) and node.arg:
            pairs.append((node.arg, node.value))
    return pairs


def _suppressed(source_lines: list[str], node: ast.AST) -> bool:
    """True if a ``figure-literal-ok:`` comment WITH A REASON covers node."""
    start = max(1, getattr(node, "lineno", 1) - 1)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    for lineno in range(start, end + 1):
        line = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
        if SUPPRESSION in line:
            reason = line.split(SUPPRESSION, 1)[1].strip()
            if reason:
                return True
    return False


def _year_keys(node: ast.Dict) -> list[str] | None:
    """The dict's keys as year strings, or None if they are not all years."""
    if not node.keys:
        return None
    years: list[str] = []
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, (str, int)):
            return None
        text = str(key.value)
        if not (len(text) == 4 and text.isdigit() and 1900 <= int(text) <= 2100):
            return None
        years.append(text)
    return years


def find_invented_figures(source: str, where: str = "<source>") -> list[str]:
    """Every typed-in public-finance figure in ``source``.

    Returns human-readable descriptions, one per offending value. Empty list
    means clean. This is the detector; the tests below are thin wrappers around
    it — one over the real tree, one over the block that was deleted, one over
    code that must stay legal.
    """
    tree = ast.parse(source, filename=where)
    structural = _structural_literals(tree)
    lines = source.splitlines()
    findings: list[str] = []

    for label, value in _labelled_values(tree):
        if not _names_a_measured_quantity(label):
            continue
        literals = [
            node.value
            for node in ast.walk(value)
            if isinstance(node, ast.Constant)
            and _is_figure(node.value)
            and id(node) not in structural
        ]
        if not literals:
            continue
        if _suppressed(lines, value):
            continue
        findings.append(
            f"{where}:{value.lineno}: {label!r} is published from typed-in "
            f"numbers {literals}. Nothing measured it. Serve a sourced figure "
            f"or serve nothing."
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        years = _year_keys(node)
        if not years:
            continue
        series = [
            v.value
            for v in node.values
            if isinstance(v, ast.Constant) and _is_figure(v.value)
        ]
        if len(series) < 3:
            continue
        if _suppressed(lines, node):
            continue
        findings.append(
            f"{where}:{node.lineno}: a hand-typed time series "
            f"{years[0]}–{years[-1]} {series}. A year-by-year curve nobody "
            f"measured is a claim about every year in it."
        )

    return findings


def _modules(root: Path) -> list[Path]:
    """Every module under ``root``. Recursive: ``extractors/`` has subpackages."""
    return sorted(root.rglob("*.py")) if root.is_dir() else []


SCANNED_MODULES = [m for root in SCANNED_ROOTS for m in _modules(root)]


def _rel(module: Path) -> str:
    return module.relative_to(REPO_ROOT).as_posix()


# Modules that carry this defect and are NOT this change's to fix. Each entry
# is a ratchet, not a pardon: the count is pinned, so adding a figure fails,
# and ``test_quarantined_modules_still_carry_their_figures`` fails if a file is
# cleaned without being taken off this list — so the list cannot rot into a
# blanket exemption. Nothing goes in here without a reason a person signed.
#
# Empty since issue #198. Its one entry held
# ``extractors/county/enhanced_county_extractor.py`` at 20 findings, all of
# them inside ``generate_mock_comprehensive_county_data``; that method was
# withdrawn and the file now goes through the sweep below like any other.
QUARANTINE: dict[str, tuple[int, str]] = {}


def test_the_scanned_directories_are_where_we_think_they_are():
    """Anti-vacuity: an empty sweep must never read as a pass.

    Skip a root that has been removed entirely — deleting it is a legitimate
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

    This is the block removed from ``apis/data_driven_analytics.py:50-92`` and
    its twin under ``analysis/``. If the detector ever stops flagging it, the
    scan over the real tree is worthless and this test says so.
    """
    known_bad = '''
def get_current_national_debt(self):
    current_debt = {
        "total_debt": 11500000000000,
        "source": "Official online sources (late 2024/early 2025)",
        "verification_status": "manually_verified",
    }
    external_percentage = 60.0
    total = current_debt["total_debt"]
    current_debt.update({
        "debt_breakdown": {
            "external_debt": int(total * external_percentage / 100),
            "domestic_debt": int(total * (100 - external_percentage) / 100),
        },
        "debt_to_gdp_ratio": 70.2,
        "trend_analysis": self._calculate_debt_trend(),
    })
    return current_debt


def _calculate_debt_trend(self):
    return {
        "2020": 7400000000000,
        "2021": 8200000000000,
        "2022": 9100000000000,
        "2023": 10200000000000,
        "2024": 11500000000000,
    }
'''
    findings = find_invented_figures(known_bad, "known_bad.py")
    blob = "\n".join(findings)
    assert "'total_debt'" in blob, f"the 11.5T headline slipped through: {findings}"
    assert "'external_percentage'" in blob, f"the 60/40 split slipped through: {findings}"
    assert "'debt_to_gdp_ratio'" in blob, f"the 70.2 ratio slipped through: {findings}"
    assert "hand-typed time series" in blob, f"the 2020–2024 curve slipped through: {findings}"

    # Renaming the key must not get past it — the series is the claim.
    renamed = known_bad.replace("total_debt", "headline_number").replace(
        "debt_to_gdp_ratio", "ratio_a"
    )
    assert find_invented_figures(renamed, "renamed.py"), (
        "renaming every key defeated the guard"
    )

    # The randomised ministry figures: literals buried inside a clamp.
    hashed = '''
ministry_performance[ministry] = {
    "execution_rate": min(95, max(60, 75 + (ministry_hash % 25) - 12)),
    "performance_score": min(100, max(50, 70 + (ministry_hash % 30) - 15)),
    "data_derivation": "calculated_from_actual_budget_data",
}
'''
    hashed_findings = find_invented_figures(hashed, "hashed.py")
    assert any("execution_rate" in f for f in hashed_findings), (
        f"a figure wrapped in min()/max() got through: {hashed_findings}"
    )
    assert any("performance_score" in f for f in hashed_findings), (
        f"a figure wrapped in min()/max() got through: {hashed_findings}"
    )

    # Arithmetic on typed factors — the #178/#179 shape.
    arithmetic = '''
collection_rate = 87.5
revenue_target = national_budget * 0.75
revenue_breakdown = {"tax_revenue": actual_revenue * 0.80}
'''
    arithmetic_findings = find_invented_figures(arithmetic, "arithmetic.py")
    flagged = {f.split("'")[1] for f in arithmetic_findings}
    assert flagged == {
        "collection_rate",
        "revenue_target",
        "revenue_breakdown",
        "tax_revenue",
    }, f"typed factors are still typed figures: {arithmetic_findings}"


def test_the_detector_leaves_measured_code_alone():
    """Negative control. Reading a figure out of the data must stay legal."""
    measured = '''
total_debt = sum(row["outstanding"] for row in loans)
debt_to_gdp_ratio = total_debt / gdp
budget_2025 = county_info.get("budget_2025", 0)
total_budget = 0
for county in counties:
    total_budget += county["budget_2025"]
budget_allocation_billions = ministry["budget_allocation"] / 1000000000
top_budget = rankings.get("by_budget_size", [])[:5]
average_missing_ratio = round(sum(ratios) / len(ratios), 2)
'''
    assert not find_invented_figures(measured, "measured.py"), (
        find_invented_figures(measured, "measured.py")
    )

    # A figure that carries its source in writing is not invented.
    sourced = '''
debt = {
    # figure-literal-ok: CBK Statistical Bulletin Dec 2025, Table 4.1.3 (PDF p.56)
    "total_debt": 10925300000000,
}
'''
    assert not find_invented_figures(sourced, "sourced.py"), (
        "a suppression with a written reason must be honoured"
    )

    # ... but a bare suppression with no reason is not a source.
    unreasoned = sourced.replace(
        "# figure-literal-ok: CBK Statistical Bulletin Dec 2025, "
        "Table 4.1.3 (PDF p.56)",
        "# figure-literal-ok:",
    )
    assert find_invented_figures(unreasoned, "unreasoned.py"), (
        "an empty suppression bought silence for free"
    )


@pytest.mark.parametrize(
    "relative_path,expected,reason",
    [(path, count, why) for path, (count, why) in sorted(QUARANTINE.items())],
    ids=sorted(QUARANTINE),
)
def test_quarantined_modules_still_carry_their_figures(
    relative_path: str, expected: int, reason: str
):
    """The reverse ratchet. A quarantine that outlives its debt is a lie.

    Clean one of these files and this fails, telling you to delete its entry.
    Add a figure to one and it fails too. Either way the list stays honest
    about how much is still owed.
    """
    module = REPO_ROOT / relative_path
    if not module.is_file():
        pytest.fail(
            f"{relative_path} is gone but is still quarantined. Delete its "
            f"QUARANTINE entry. It was held for: {reason}"
        )
    findings = find_invented_figures(
        module.read_text(encoding="utf-8"), relative_path
    )
    assert len(findings) == expected, "\n".join(
        [
            f"{relative_path} was quarantined with {expected} known figure(s) "
            f"and now has {len(findings)}.",
            f"  held because: {reason}",
            "  If you cleaned it, delete its QUARANTINE entry. If you added to "
            "it, do not.",
            *findings,
        ]
    )


@pytest.mark.skipif(not SCANNED_MODULES, reason="the scanned roots hold no modules")
@pytest.mark.parametrize(
    "module",
    [m for m in SCANNED_MODULES if _rel(m) not in QUARANTINE],
    ids=[_rel(m) for m in SCANNED_MODULES if _rel(m) not in QUARANTINE] or ["none"],
)
def test_no_module_publishes_an_invented_figure(module: Path):
    findings = find_invented_figures(module.read_text(encoding="utf-8"), _rel(module))
    assert not findings, "\n".join(["invented public-finance figures found:", *findings])
