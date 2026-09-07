"""No module under ``apis/``, ``analysis/`` or ``extractors/`` may derive a
value from ``hash()``, from the clock, or from a random draw.

On 2026-09-07, ``extractors/government/oag_audit_extractor.py`` manufactured
audit findings about named county governments out of ``hash()``::

    num_queries = hash(county) % 4 + 2                     # queries per county
    base_amount = (hash(f"{county}-{i}") % 50000000) + 1000000        # KSh
    "case_id": f"MF{hash(f'{county}-{i}') % 9999:04d}"
    "date_raised": f"2024-{(hash(county) % 12) + 1:02d}-..."
    "severity": ["High", "Medium", "Low"][hash(f"{county}-{i}") % 3]
    return efforts[: hash(str(time.time())) % 3 + 1]

and ``comprehensive_government_extractor.py`` did the same for ministry money::

    ministry_hash = hash(ministry)
    "budget_allocation": (ministry_hash % 500000000000) + 100000000000
    "pending_bills":     (ministry_hash % 10000000000) + 1000000000

``hash()`` on a ``str`` is salted per process. Three fresh interpreters put the
Ministry of Health's budget allocation at KSh 116.4 Bn, 147.3 Bn and 338.1 Bn.
The last line above is worse still: seeded on ``time.time()``, it varies
*within* a single run.

WHY THIS RULE EXISTS BESIDE THE OTHER TWO. The county guard
(``test_apis_no_invented_county_rankings.py``) keys on county *names*; the
figure guard (``test_apis_no_invented_national_figures.py``) keys on a numeric
literal under a *label* that denotes a measured quantity. Neither sees this.
Run the figure detector over ``oag_audit_extractor.py`` as it stood and it
returns exactly ONE finding, for ``percentage_of_budget`` — because
``num_queries``, ``case_id``, ``severity``, ``date_raised`` and ``amount`` are
not words on its subject list. Seventeen ``hash()`` sites, sixteen of them
invisible. A label heuristic cannot be made complete; "this number came from a
pseudo-random generator" needs no vocabulary at all.

THE RULE. Three sources are barred outright wherever they appear in the
scanned roots:

* ``hash(...)``. It is a per-process pseudo-random function of its argument.
  Nothing it returns describes the world. For a stable digest, use ``hashlib``.
* a ``random`` draw. There is no instance of this in the tree today; it is
  named because a rule that bars only ``hash()`` is defeated by one import.
* a clock reading used as a NUMBER — feeding ``%`` or ``//``, or standing in a
  subscript or slice. Reading the clock is otherwise fine and common here:
  ``datetime.now().isoformat()`` stamps a record, ``(end - start)`` measures a
  run. Those are timestamps and durations, and they stay legal. It is the
  clock as a *seed* that is barred.

THIS RULE MUST PARSE, NOT GREP, and there are two independent reasons.

The first is that a text scan is wrong in the other direction: PR #191's own
withdrawal notes, in ``apis/data_driven_analytics.py:13``,
``analysis/data_driven_analytics.py:13``, ``apis/modernized_api.py:18`` and
``analysis/ARCHITECTURE_IMPROVEMENTS_SUMMARY.py:14``, contain the characters
``hash(name)`` while *describing* the defect they removed. A ``grep`` guard
would go red on the paperwork and stay red until someone deleted the record.
``test_a_text_scan_would_flag_the_paperwork`` below pins that.

The second is the one issue #193 raised, though not quite for the stated
reason. #193 says pytest pins ``PYTHONHASHSEED``, so a test asserting these
values move would fail while the defect was live. In THIS repo it does not:
``pytest-randomly`` is not installed and ``os.environ["PYTHONHASHSEED"]`` is
unset under the runner. The conclusion survives on firmer ground anyway —
``hash()`` is constant *within* a process whatever the seed, so a run-it-twice
test in one interpreter finds these values rock steady no matter what, and a
CI that did pin the seed would freeze them across processes too. A behavioural
test here measures the harness. So the guard below reads the source.

The instability is real, and ``test_the_withdrawn_expressions_move_between_
processes`` demonstrates it honestly, by shelling out to fresh interpreters
with the seed unset. That test is a demonstration of the motive, not the
guard: it runs against a string, never against the tree.

ESCAPE HATCH, following ``local/no-zero-fallback-on-published-figure``
(7b5d366) and the two guards beside this file: a suppression must carry a
written reason. Put

    # nondeterminism-ok: <why this value need not describe anything>

on the line the call opens, or the line above it.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_ROOTS = (
    REPO_ROOT / "apis",
    REPO_ROOT / "analysis",
    REPO_ROOT / "extractors",
)

SUPPRESSION = "nondeterminism-ok:"

# A clock reading. Matched on the tail of the dotted callee, so ``time.time``,
# ``datetime.datetime.now`` and ``dt.now`` all land.
CLOCK_SUFFIXES = (
    "time.time",
    "time.time_ns",
    "time.monotonic",
    "time.monotonic_ns",
    "time.perf_counter",
    "time.perf_counter_ns",
    "time.process_time",
    "datetime.now",
    "datetime.utcnow",
    "datetime.today",
    "date.today",
)
# ``from time import time`` — a bare call by one of these names is a clock.
CLOCK_BARE = ("time", "time_ns", "monotonic", "perf_counter", "process_time")

# ``from random import randint`` — the module's public draw functions.
RANDOM_FUNCTIONS = (
    "random",
    "randint",
    "randrange",
    "choice",
    "choices",
    "shuffle",
    "sample",
    "uniform",
    "gauss",
    "betavariate",
    "getrandbits",
)


def _dotted(node: ast.AST) -> str:
    """``time.time`` for ``ast.Attribute(Name('time'), 'time')``; '' if not a name."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _random_names(tree: ast.AST) -> set[str]:
    """Bare names bound by ``from random import x`` in this module."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "random":
            for alias in node.names:
                bound.add(alias.asname or alias.name)
    return bound


def _clock_names(tree: ast.AST) -> set[str]:
    """Bare names bound by ``from time import time`` in this module."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "time":
            for alias in node.names:
                if alias.name in CLOCK_BARE:
                    bound.add(alias.asname or alias.name)
    return bound


def _is_clock_call(node: ast.AST, clock_names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    dotted = _dotted(node.func)
    if any(dotted == s or dotted.endswith("." + s) for s in CLOCK_SUFFIXES):
        return True
    return isinstance(node.func, ast.Name) and node.func.id in clock_names


def _seed_positions(tree: ast.AST) -> list[ast.AST]:
    """Expressions where a value is being used as a NUMBER to pick with.

    A modulo or floor-division operand, or a subscript index. ``"%s" % x`` is
    string formatting, not arithmetic, and is skipped.
    """
    spots: list[ast.AST] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.FloorDiv)):
            if isinstance(node.op, ast.Mod) and isinstance(
                node.left, (ast.JoinedStr,)
            ):
                continue
            if (
                isinstance(node.op, ast.Mod)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, (str, bytes))
            ):
                continue
            spots.append(node)
        elif isinstance(node, ast.Subscript):
            spots.append(node.slice)
    return spots


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    """Map every node id to the name of the function it sits in."""
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                owner.setdefault(id(child), node.name)
    return owner


def _suppressed(source_lines: list[str], node: ast.AST) -> bool:
    """True if a ``nondeterminism-ok:`` comment WITH A REASON covers node."""
    start = max(1, getattr(node, "lineno", 1) - 1)
    end = getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)
    for lineno in range(start, end + 1):
        line = source_lines[lineno - 1] if lineno <= len(source_lines) else ""
        if SUPPRESSION in line:
            reason = line.split(SUPPRESSION, 1)[1].strip()
            if reason:
                return True
    return False


def find_nondeterministic_sources(source: str, where: str = "<source>") -> list[str]:
    """Every ``hash()``, random draw and clock-as-seed in ``source``.

    Returns human-readable descriptions, one per offending expression. Empty
    list means clean. This is the detector; the tests below are thin wrappers
    around it — over the real tree, over the withdrawn payload, and over code
    that must stay legal.
    """
    tree = ast.parse(source, filename=where)
    lines = source.splitlines()
    owner = _enclosing_functions(tree)
    random_names = _random_names(tree)
    clock_names = _clock_names(tree)
    findings: list[str] = []

    def _where(node: ast.AST) -> str:
        fn = owner.get(id(node))
        text = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        if len(text) > 90:
            text = text[:87] + "..."
        return (
            f"{where}:{node.lineno}:{node.col_offset}: "
            + (f"in {fn}(): " if fn else "")
            + text
        )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _suppressed(lines, node):
            continue

        if isinstance(node.func, ast.Name) and node.func.id == "hash":
            findings.append(
                _where(node)
                + "\n    derives from hash(), which is a per-process "
                "pseudo-random function of its argument and describes nothing. "
                "Measure it, or do not publish it. For a stable digest use "
                "hashlib."
            )
            continue

        dotted = _dotted(node.func)
        is_random = dotted.startswith("random.") or (
            isinstance(node.func, ast.Name)
            and node.func.id in random_names
            and node.func.id in RANDOM_FUNCTIONS
        )
        if is_random:
            findings.append(
                _where(node)
                + "\n    derives from a random draw. A figure nobody measured "
                "is invented whether the dice are honest or not."
            )

    for spot in _seed_positions(tree):
        if spot is None:
            continue
        clocks = [n for n in ast.walk(spot) if _is_clock_call(n, clock_names)]
        if not clocks:
            continue
        if _suppressed(lines, spot) or any(_suppressed(lines, c) for c in clocks):
            continue
        findings.append(
            _where(clocks[0])
            + "\n    uses the clock as a number to pick with. A timestamp or a "
            "duration is a measurement; the clock modulo something is a "
            "randomiser that changes within a single run."
        )

    return sorted(set(findings))


def _modules(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py")) if root.is_dir() else []


SCANNED_MODULES = [m for root in SCANNED_ROOTS for m in _modules(root)]


def _rel(module: Path) -> str:
    return module.relative_to(REPO_ROOT).as_posix()


# Modules that carry this defect and are NOT this change's to fix. Each entry
# is a ratchet, not a pardon: the count is pinned, so adding a site fails, and
# `test_quarantined_modules_still_carry_their_debt` fails if a file is cleaned
# without being taken off this list. Nothing may be added here without an
# issue that owns it.
#
# Empty since issue #198. Its one entry held
# ``extractors/county/enhanced_county_extractor.py`` at 2 sites — a population
# and an audit rating, both ``hash(county)`` — and both went with
# ``generate_mock_comprehensive_county_data``. The file now goes through the
# sweep below like any other.
QUARANTINE: dict[str, tuple[int, str]] = {}


def test_the_scanned_roots_are_where_we_think_they_are():
    """Anti-vacuity: an empty sweep must never read as a pass.

    Skip a root that has been removed entirely — deleting one is a legitimate
    outcome and the owner's call — but fail if a root exists and the scan finds
    nothing in it, and fail if every root has vanished at once.
    """
    surviving = [root for root in SCANNED_ROOTS if root.is_dir()]
    if not surviving:
        pytest.skip("apis/, analysis/ and extractors/ have all been removed")
    for root in surviving:
        assert _modules(root), (
            f"{root.name}/ exists but holds no .py files — its scan would be vacuous"
        )
    assert SCANNED_MODULES, "no modules collected — the sweep would be silent"


def test_the_detector_catches_the_payload_it_was_written_for():
    """Positive control. Proves a green run below means clean, not blind.

    These are the expressions withdrawn from
    ``extractors/government/oag_audit_extractor.py`` and
    ``extractors/government/comprehensive_government_extractor.py``.
    """
    known_bad = '''
import time

def generate_county_audit_queries(self):
    for county in self.counties:
        num_queries = hash(county) % 4 + 2
        for i in range(num_queries):
            base_amount = (hash(f"{county}-{i}") % 50000000) + 1000000
            query = {
                "case_id": f"MF{hash(f'{county}-{i}') % 9999:04d}",
                "amount": base_amount,
                "date_raised": f"2024-{(hash(county) % 12) + 1:02d}",
                "severity": ["High", "Medium", "Low"][hash(f"{county}-{i}") % 3],
            }

def _generate_recovery_efforts(self):
    efforts = ["Investigation committee established", "Forensic audit initiated"]
    return efforts[: hash(str(time.time())) % 3 + 1]

def _generate_ministry_performance(self):
    for ministry in ministries:
        ministry_hash = hash(ministry)
        ministry_data[ministry] = {
            "budget_allocation": (ministry_hash % 500000000000) + 100000000000,
            "pending_bills": (ministry_hash % 10000000000) + 1000000000,
        }
'''
    findings = find_nondeterministic_sources(known_bad, "known_bad.py")
    blob = "\n".join(findings)

    assert blob.count("derives from hash()") == 7, (
        f"expected all seven hash() calls: {findings}"
    )
    assert "uses the clock as a number to pick with" in blob, (
        f"the time.time()-seeded slice slipped through: {findings}"
    )

    # Two hash() calls on ONE line must count twice. This is the real
    # ``date_raised`` line, and it is why findings carry a column: a
    # per-line finding would collapse these into one and the QUARANTINE
    # ratchet below would not notice a site being added to a flagged line.
    two_on_one = (
        'd = f"2024-{(hash(county) % 12) + 1:02d}-'
        '{(hash(f\'{county}-{i}\') % 28) + 1:02d}"\n'
    )
    assert len(find_nondeterministic_sources(two_on_one, "two.py")) == 2, (
        find_nondeterministic_sources(two_on_one, "two.py")
    )
    for fn in (
        "generate_county_audit_queries",
        "_generate_recovery_efforts",
        "_generate_ministry_performance",
    ):
        assert f"in {fn}()" in blob, f"{fn} was not named in {findings}"

    # The label heuristics of the two guards beside this file cannot see most
    # of this, which is the reason this rule exists. Renaming every key must
    # not help — the rule never reads a key.
    renamed = (
        known_bad.replace("budget_allocation", "field_a")
        .replace("amount", "field_b")
        .replace("severity", "field_c")
    )
    assert len(find_nondeterministic_sources(renamed, "renamed.py")) == len(findings), (
        "renaming every key changed the verdict — the rule is reading labels"
    )

    # A random draw is the same defect with better dice.
    drawn = '''
import random
from random import randint
budget = random.randint(100, 600) * 1000000000
queries = randint(2, 20)
'''
    drawn_findings = find_nondeterministic_sources(drawn, "drawn.py")
    assert len(drawn_findings) == 2, f"a random draw got through: {drawn_findings}"

    # An empty suppression buys nothing.
    unreasoned = "x = hash(county) % 4  # nondeterminism-ok:"
    assert find_nondeterministic_sources(unreasoned, "unreasoned.py"), (
        "an empty suppression bought silence for free"
    )


def test_the_detector_leaves_measurement_and_timestamps_alone():
    """Negative control. Stamping a record and timing a run must stay legal."""
    legal = '''
import time
import hashlib
from datetime import datetime

def run(self):
    start_time = datetime.now()
    reports = self.extract()
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    elapsed = time.time() - self.started_at
    digest = hashlib.sha256(url.encode()).hexdigest()[:12]
    return {
        "timestamp": datetime.now().isoformat(),
        "extracted_date": datetime.now().isoformat(),
        "extraction_duration": duration,
        "elapsed": "%.1f seconds" % elapsed,
        "county_reports": len(reports.get("county", [])),
        "page": reports["county"][0],
        "recent": reports[-5:],
        "bucket": len(reports) % 4,
    }
'''
    assert not find_nondeterministic_sources(legal, "legal.py"), (
        find_nondeterministic_sources(legal, "legal.py")
    )

    # A value that carries its reason in writing is signed for.
    sourced = (
        "bucket = hash(key) % 16  "
        "# nondeterminism-ok: in-memory shard, never published\n"
    )
    assert not find_nondeterministic_sources(sourced, "sourced.py"), (
        "a suppression with a written reason must be honoured"
    )


def test_a_text_scan_would_flag_the_paperwork():
    """The rule must parse. Grep would go red on #191's withdrawal notes.

    ``apis/data_driven_analytics.py`` records, in its module docstring, that
    ministry rates "were abs(hash(name)) % 25". Those characters are a
    description of a removed defect. A guard that could not tell a docstring
    from a call would force the record to be deleted to go green.
    """
    paperwork = REPO_ROOT / "apis" / "data_driven_analytics.py"
    if not paperwork.is_file():
        pytest.skip("apis/data_driven_analytics.py has been removed")
    source = paperwork.read_text(encoding="utf-8")
    assert "hash(" in source, (
        "this test is pinned to #191's withdrawal note; the note is gone, so "
        "either restore the anchor or retire this test"
    )
    assert not find_nondeterministic_sources(source, "apis/data_driven_analytics.py"), (
        "the detector flagged prose describing a defect that was already removed"
    )


def test_the_withdrawn_expressions_move_between_processes():
    """A demonstration of the motive, not the guard.

    Runs the withdrawn ministry expressions in fresh interpreters with
    ``PYTHONHASHSEED`` unset. Kept away from the tree deliberately: the guard
    above reads source, and nothing here may depend on this being runnable.
    """
    snippet = (
        "h = hash('Health');"
        "print((h % 500000000000) + 100000000000, (h % 10000000000) + 1000000000)"
    )
    env = {k: v for k, v in os.environ.items() if k != "PYTHONHASHSEED"}
    seen = set()
    for _ in range(6):
        out = subprocess.run(
            [sys.executable, "-c", snippet],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )
        assert out.returncode == 0, out.stderr
        seen.add(out.stdout.strip())

    if len(seen) == 1:
        pytest.skip(
            "this interpreter is not salting str hashes (PYTHONHASHSEED pinned "
            "outside our control) — the source rule above is unaffected"
        )
    assert len(seen) > 1, (
        "six fresh interpreters agreed on the Ministry of Health's budget: "
        f"{seen}"
    )


@pytest.mark.parametrize(
    "relative_path,expected,reason",
    [(p, c, r) for p, (c, r) in sorted(QUARANTINE.items())],
    ids=sorted(QUARANTINE),
)
def test_quarantined_modules_still_carry_their_debt(
    relative_path: str, expected: int, reason: str
):
    """The reverse ratchet. A quarantine that outlives its debt is a lie.

    If one of these files is cleaned, this fails and tells you to delete its
    entry — so the list cannot quietly grow into a blanket exemption.
    """
    module = REPO_ROOT / relative_path
    if not module.is_file():
        pytest.fail(
            f"{relative_path} is gone but is still quarantined. Delete its "
            f"QUARANTINE entry. It was held for: {reason}"
        )
    findings = find_nondeterministic_sources(
        module.read_text(encoding="utf-8"), relative_path
    )
    assert len(findings) == expected, "\n".join(
        [
            f"{relative_path} was quarantined with {expected} known site(s) and "
            f"now has {len(findings)}.",
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
def test_no_module_derives_a_value_from_hash_or_the_clock(module: Path):
    findings = find_nondeterministic_sources(
        module.read_text(encoding="utf-8"), _rel(module)
    )
    assert not findings, "\n".join(
        ["values derived from hash(), the clock or a random draw:", *findings]
    )
