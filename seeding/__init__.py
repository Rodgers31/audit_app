"""Top-level seeding shim for running `python -m seeding.cli` from repo root.

This file exists solely so the seed workflow can run from the repository root.
It should NOT be imported during pytest — backend/conftest.py ensures only
backend/ is on sys.path when tests run.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add backend/ to path so `from seeding.X import Y` resolves to backend/seeding/X
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
