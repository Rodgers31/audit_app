"""Execute prerequisite PostgreSQL exclusion cases on an owned disposable DB."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--xml", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    sys.path[:0] = [str(root / "backend"), str(root / "backend/tests")]
    from batch11_bootstrap_fixture.postgres import postgres
    from sqlalchemy import create_engine
    from models import Base
    with postgres(legacy=True) as url:
        engine = create_engine(url)
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()
        # The historical fixture requires this exact inert local URL. It is
        # created here, never inherited from the caller's environment.
        os.environ["BATCH7_ETL_TEST_DATABASE_URL"] = url
        import pytest
        result = pytest.main([
            "tests/test_batch8_exclusion_scope.py", "tests/test_batch8_exclusion_review.py",
            "-vv", "-s", "--junitxml=" + str(args.xml),
            "--basetemp=" + str(args.xml.parent / (args.xml.stem + "-tmp")),
            "-o", "cache_dir=" + str(args.xml.parent / (args.xml.stem + "-cache")),
        ])
    return result


if __name__ == "__main__":
    raise SystemExit(main())
