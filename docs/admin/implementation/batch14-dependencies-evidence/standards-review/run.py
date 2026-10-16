"""Portable standards replay; see ../README.md for fixture preparation."""
import runpy
import sys
from pathlib import Path

sys.argv.insert(1, "standards")
runpy.run_path(str(Path(__file__).resolve().parents[1] / "portable-replay.py"), run_name="__main__")
