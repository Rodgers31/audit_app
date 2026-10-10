"""Run the complete canonical core inventory with explicit ETL package ownership."""
import argparse
import importlib.util
import os
from pathlib import Path
import socket
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", choices=("backend", "legacy"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    out = args.out.absolute()
    if out.exists() or out.resolve() != out or root == out or root in out.parents:
        raise ValueError("Fresh external output required")
    out.mkdir()
    # No external transport is needed for the mocked core suite. Owned process
    # fixtures use loopback; Docker is controlled through its local CLI/socket.
    original = socket.socket.connect
    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("Core replay external transport refused")
        return original(sock, address)
    socket.socket.connect = local_connect
    path = root / ".github/scripts/run_backend_tests.py"
    spec = importlib.util.spec_from_file_location("canonical_backend_runner", path)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    sys.path.insert(0, str(root / "backend"))
    runner.bind_package("seeding", root / "backend/seeding")
    runner.bind_package("etl", root / "etl" if args.cohort == "legacy" else root / "backend/etl")
    os.environ["PYTHONPATH"] = runner.descendant_environment(args.cohort, out)
    os.environ["COVERAGE_FILE"] = str(out / ".coverage")
    import pytest
    files = runner.test_inventory()[args.cohort]
    return pytest.main([*files, "-o", "addopts=", "-vv", "-s", "-m", "not slow",
        "--junitxml=" + str(out / "results.xml"), "--basetemp=" + str(out / "tmp"),
        "-o", "cache_dir=" + str(out / "cache")],
        plugins=[runner.CollectionReceipt(args.cohort, files, out / "collection.json")])


if __name__ == "__main__":
    raise SystemExit(main())
