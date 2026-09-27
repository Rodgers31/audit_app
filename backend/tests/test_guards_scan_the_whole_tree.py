"""The source guards read the whole tree, and this file proves the walk does.

Issue #206: the ``hash()`` guard and the county-selection guard scanned an
inclusion list of three directories, so two generators at the repo root — one
alleging missing funds against five named counties — were green by
construction. ``tests/_repo_tree.py`` replaced the list with a walk of the whole
tree minus a written exclusion list. These tests pin the walk itself, because a
guard is only as wide as the set of files it is handed:

* a file at the root, or in a directory that did not exist yesterday, is read;
* what is skipped is exactly what the exclusion list says, and every entry in
  it still points at something;
* no tracked module is silently dropped (checked against ``git ls-files``);
* every scanned module parses — an AST rule cannot see into a file it cannot
  parse, so an unparseable file is a hole, not a pass.
"""

from __future__ import annotations

import ast
import os
import subprocess

import pytest

from tests._repo_tree import (
    ENVIRONMENT_DIR_NAMES,
    REPO_EXCLUSIONS,
    REPO_ROOT,
    VIRTUALENV_MARKER,
    python_modules,
    rel,
)

MODULES = python_modules()


def _plant(root, relative: str, text: str = "x = 1\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_the_walk_reads_the_root_and_a_directory_nobody_has_made_yet(tmp_path):
    """The #206 failure, replayed: a file outside any named directory."""
    _plant(tmp_path, "county_analytics_generator.py")
    _plant(tmp_path, "brand_new_package/deeper/neutral_name.py")
    _plant(tmp_path, "apis/still_read.py")

    got = {rel(m, tmp_path) for m in python_modules(tmp_path)}

    assert got == {
        "county_analytics_generator.py",
        "brand_new_package/deeper/neutral_name.py",
        "apis/still_read.py",
    }


def test_the_walk_skips_exactly_what_the_exclusion_list_says(tmp_path):
    """Negative control: dependencies, caches, other checkouts, the tests."""
    _plant(tmp_path, "kept.py")
    _plant(tmp_path, "frontend/node_modules/pkg/setup.py")
    _plant(tmp_path, ".claude/worktrees/other-branch/apis/generator.py")
    _plant(tmp_path, "backend/tests/test_fixture_with_counties.py")
    _plant(tmp_path, "backend/__pycache__/stray.py")
    # A virtualenv is recognised by its marker, not its name.
    _plant(tmp_path, "backend/any_name_at_all/" + VIRTUALENV_MARKER, "home = /x\n")
    _plant(tmp_path, "backend/any_name_at_all/lib/site-packages/dep.py")
    # A directory that merely LOOKS like an exclusion is still read.
    _plant(tmp_path, "etl/tests_helpers.py")
    _plant(tmp_path, "tools/backend/tests/not_the_excluded_path.py")

    got = {rel(m, tmp_path) for m in python_modules(tmp_path)}

    assert got == {
        "kept.py",
        "etl/tests_helpers.py",
        "tools/backend/tests/not_the_excluded_path.py",
    }


def test_every_repo_exclusion_still_exists():
    """A stale exclusion silently covers whatever is created there next."""
    for path, reason in REPO_EXCLUSIONS.items():
        assert (REPO_ROOT / path).is_dir(), (
            f"{path} is excluded from every source guard but no longer exists. "
            f"Delete the entry. It was excluded because: {reason}"
        )
        assert reason.strip(), f"{path} is excluded without a written reason"
    for name, reason in ENVIRONMENT_DIR_NAMES.items():
        assert reason.strip(), f"{name} is pruned without a written reason"


def test_the_walk_drops_no_tracked_module():
    """Every tracked ``*.py`` outside the exclusions is in the walk.

    The walk is a filesystem walk so that a file is covered before anyone
    commits it; this is the check that it never loses one ``git`` knows about.
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"git is not runnable here ({exc}); the tmp-tree tests still pin the walk")
    if out.returncode != 0:
        pytest.skip(
            f"git ls-files exited {out.returncode}: {out.stderr.strip()[:200]} — "
            "the tmp-tree tests still pin the walk"
        )

    tracked = {p for p in out.stdout.split("\0") if p}
    assert tracked, "git ls-files returned nothing — this check would be vacuous"
    expected = {
        p
        for p in tracked
        if not any(p == ex or p.startswith(ex + "/") for ex in REPO_EXCLUSIONS)
        and not any(part in ENVIRONMENT_DIR_NAMES for part in p.split("/")[:-1])
        # a tracked file deleted in the working tree is not there to read
        and (REPO_ROOT / p).is_file()
    }
    walked = {rel(m) for m in MODULES}
    missing = sorted(expected - walked)
    assert not missing, (
        "tracked modules the source guards never read:\n  " + "\n  ".join(missing)
    )


def test_nothing_outside_the_tests_imports_them():
    """``backend/tests`` is excluded on the premise that it never ships.

    If app code ever imports from it, a fixture becomes a payload and the
    exclusion becomes a hole. This keeps the premise true.
    """
    offenders = []
    for module in MODULES:
        try:
            tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        except SyntaxError:
            continue  # reported by the parse test below
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "tests" or node.module.startswith("tests.")
            ):
                offenders.append(f"{rel(module)}:{node.lineno}: from {node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "tests" or alias.name.startswith("tests."):
                        offenders.append(f"{rel(module)}:{node.lineno}: import {alias.name}")
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("module", MODULES, ids=[rel(m) for m in MODULES])
def test_every_scanned_module_parses(module):
    """An AST guard cannot see into a file it cannot parse.

    Without this, a syntax error would make a file invisible to every source
    rule at once — the same blind spot as a missing directory, one file wide.
    """
    source = module.read_text(encoding="utf-8")
    try:
        ast.parse(source, filename=rel(module))
    except SyntaxError as exc:
        pytest.fail(
            f"{rel(module)}:{exc.lineno}: does not parse ({exc.msg}), so no "
            "source guard can read it. Fix it or delete it."
        )


def test_the_walk_is_not_empty_and_reaches_the_root():
    walked = {rel(m) for m in MODULES}
    assert "backend/main.py" in walked
    assert any("/" not in p for p in walked), "no module at the repo root was read"
    assert os.sep not in "".join(ENVIRONMENT_DIR_NAMES), "exclusions are names, not paths"
