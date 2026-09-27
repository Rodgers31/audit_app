"""The set of Python modules a source-scanning guard must read: all of them.

Issue #206. The ``hash()`` guard and the county-selection guard each listed
three directories to scan — ``apis/``, ``analysis/``, ``extractors/`` — and
were green while ``county_analytics_generator.py`` sat at the repo root
alleging missing public money against five named counties. An inclusion list
is a blind spot for everything it does not name, and it grows one silently
every time someone adds a file at the root or starts a new directory. A guard
with a blind spot reads as coverage.

So the guards scan the WHOLE tree and this module says, in writing, what they
do not read and why. Two kinds of exclusion, kept apart on purpose:

* ``ENVIRONMENT_DIR_NAMES`` — directories that are not this repo's source at
  all (a dependency tree, a cache, another branch's checkout). Matched by name
  wherever they sit, and allowed to be absent: CI has no ``.claude/`` and no
  virtualenv inside the checkout. A virtualenv is recognised by its
  ``pyvenv.cfg`` rather than its name, so ``.venv313`` and ``venv`` and
  whatever comes next are all caught without a naming convention.
* ``REPO_EXCLUSIONS`` — paths that ARE this repo's source and are skipped
  deliberately. Each carries its reason, and each must exist: an exclusion
  that no longer matches anything is a stale line that would silently cover
  whatever is created at that path next
  (``test_every_repo_exclusion_still_exists``).

Everything else is scanned. A new directory is covered the moment it exists.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Not this repo's source. Pruned by directory name at any depth.
ENVIRONMENT_DIR_NAMES: dict[str, str] = {
    ".git": "version-control internals",
    "node_modules": "npm dependency tree under frontend/ — third-party code",
    "__pycache__": "bytecode caches",
    ".pytest_cache": "pytest's cache",
    ".mypy_cache": "mypy's cache",
    ".ruff_cache": "ruff's cache",
    ".next": "Next.js build output",
    ".claude": (
        "agent tooling. In the main checkout, .claude/worktrees/ holds whole "
        "checkouts of OTHER branches; scanning them would judge this tree by "
        "someone else's in-flight work"
    ),
}

#: A directory holding this file is a virtualenv, whatever it is called.
VIRTUALENV_MARKER = "pyvenv.cfg"

#: This repo's own source, skipped on purpose. Every key must exist.
REPO_EXCLUSIONS: dict[str, str] = {
    "backend/tests": (
        "test inputs contain the barred patterns deliberately: parser fixtures "
        "name real counties, and each guard carries the payload it was written "
        "for as a positive control. Nothing outside backend/tests imports from "
        "it (test_nothing_outside_the_tests_imports_them)"
    ),
}


def _is_pruned(directory: Path, root: Path) -> bool:
    if directory.name in ENVIRONMENT_DIR_NAMES:
        return True
    if (directory / VIRTUALENV_MARKER).is_file():
        return True
    rel = directory.relative_to(root).as_posix()
    return rel in REPO_EXCLUSIONS


def python_modules(root: Path = REPO_ROOT) -> list[Path]:
    """Every ``*.py`` under ``root`` that is not excluded above, sorted.

    ``root`` is a parameter so the walk itself can be tested against a
    planted tree; the guards always call it with the default.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not _is_pruned(here / d, root))
        found.extend(here / name for name in filenames if name.endswith(".py"))
    return sorted(found)


def rel(module: Path, root: Path = REPO_ROOT) -> str:
    return module.relative_to(root).as_posix()
