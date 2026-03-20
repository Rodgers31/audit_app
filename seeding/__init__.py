"""Root-level seeding shim — immediately replaces itself with backend/seeding.

This file exists so `python -m seeding.cli` works from the repository root.
On import, it replaces sys.modules['seeding'] with the real backend/seeding
package, making all submodules (pdf_parsers, config, http_client, etc.) work
transparently regardless of where Python is run from.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BACKEND_SEEDING_DIR = _REPO_ROOT / "backend" / "seeding"
_BACKEND_DIR = str(_REPO_ROOT / "backend")

# Ensure backend/ is on sys.path
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Load the real backend/seeding package and replace ourselves in sys.modules
_spec = importlib.util.spec_from_file_location(
    "seeding",
    str(_BACKEND_SEEDING_DIR / "__init__.py"),
    submodule_search_locations=[str(_BACKEND_SEEDING_DIR)],
)
if _spec and _spec.loader:
    _real = importlib.util.module_from_spec(_spec)
    _real.__path__ = [str(_BACKEND_SEEDING_DIR)]  # type: ignore[attr-defined]
    _real.__package__ = "seeding"
    sys.modules["seeding"] = _real
    _spec.loader.exec_module(_real)  # type: ignore[union-attr]
