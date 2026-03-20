"""Test-level conftest ensuring backend/ is on sys.path before any imports.

NOTE: Do NOT add the repo root to sys.path here — the root contains a stub
`seeding/` package that shadows `backend/seeding/` and breaks imports.
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
