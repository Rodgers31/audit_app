"""Test-level conftest ensuring backend/ is on sys.path before any imports."""
import os
import sys

# Ensure backend/ directory is on sys.path so `seeding`, `routers`, etc. resolve
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
