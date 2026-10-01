"""Test-level conftest ensuring backend/ is on sys.path before any imports.

NOTE: Do NOT add the repo root to sys.path here — the root contains a stub
`seeding/` package that shadows `backend/seeding/` and breaks imports.
"""
import os
import sys

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def pipeline_health_database(tmp_path, monkeypatch):
    """Give the health worker its own factory, never a request-owned session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import database
    from models import Base

    db_path = tmp_path / "pipeline-health.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    try:
        yield engine
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)
