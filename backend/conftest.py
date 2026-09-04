"""
Shared test fixtures for the backend test suite.

Uses an in-memory SQLite database with JSONB→JSON compile shim so that
PostgreSQL-specific column types work.  Every test that requests a ``client``
or ``db_session`` fixture gets a **clean, isolated** database.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Text, create_engine, event
from sqlalchemy.orm import sessionmaker

# ── path setup ──────────────────────────────────────────────────────────
# Only add BACKEND_DIR — do NOT add ROOT_DIR, as the repo root contains a
# stub `seeding/` package that shadows `backend/seeding/` and breaks imports.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ── JSONB → TEXT compile shim (must be registered before metadata.create_all) ─
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):  # noqa: ARG001
    return "TEXT"


# ── rate-limiter bypass (session-wide) ──────────────────────────────────
# Every request a TestClient makes reports the same client IP ("testclient"),
# so the whole suite shares ONE 120-request/60-second window in the mounted
# RateLimitMiddleware.  A full run makes >1000 requests, so the limiter trips
# and turns ~200 arbitrary tests red — and *which* tests, because the window
# is wall-clock, differs on every run.
#
# Patching ``RateLimitMiddleware.dispatch`` from inside a per-test fixture
# does NOT work: Starlette's BaseHTTPMiddleware binds
# ``self.dispatch_func = self.dispatch`` in ``__init__``, and the middleware
# stack is built lazily on the session's first request — so the instance
# captures the real dispatch before any per-test patch is active and keeps it
# for the rest of the process.  The bypass therefore has to be installed in
# ``pytest_configure``, before the stack is ever built.
#
# The production limiter itself is still covered — see
# tests/test_rate_limiter_bypass.py, which mounts it directly and proves it
# still refuses traffic over the limit.
def pytest_configure(config):  # noqa: ARG001
    from middleware.security import RateLimitMiddleware, RedisRateLimitMiddleware

    async def _passthrough(self, request, call_next):
        return await call_next(request)

    for cls in (RateLimitMiddleware, RedisRateLimitMiddleware):
        # Keep the real implementation reachable so a test can mount the
        # limiter directly and prove it still refuses over-limit traffic.
        cls._original_dispatch = cls.dispatch
        cls.dispatch = _passthrough

    # Defensive: if anything already built the stack during import, rebind the
    # live instances too (dispatch_func was captured at construction).
    def _rebind(mw):
        seen = set()
        while mw is not None and id(mw) not in seen:
            seen.add(id(mw))
            if isinstance(mw, (RateLimitMiddleware, RedisRateLimitMiddleware)):
                mw.dispatch_func = _passthrough.__get__(mw, type(mw))
            mw = getattr(mw, "app", None)

    _rebind(getattr(app, "middleware_stack", None))


# ── outbound network guard ──────────────────────────────────────────────
# Eight tests were reaching real government/IFI hosts (api.worldbank.org,
# treasury.go.ke, cob.go.ke, centralbank.go.ke, knbs.or.ke, oagkenya.go.ke,
# imf.org).  Whether those calls succeeded, timed out or returned a WAF error
# varied per run, so the suite's result depended on the network.  Block them by
# default; a test that genuinely needs the internet opts in with
# ``@pytest.mark.network``.
#
# We block at the httpx/requests *transport* layer rather than at
# socket.connect: patching the socket corrupts machinery Starlette's TestClient
# shares, so one blocked call cascades into unrelated failures later.  At the
# transport layer the exception raised is exactly the one the seeders' own
# try/except blocks are written to handle.
_LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testserver", "testclient"})


@pytest.fixture(autouse=True)
def _no_outbound_network(request):
    """Fail any real outbound HTTP unless the test is marked ``network``."""
    if request.node.get_closest_marker("network"):
        yield
        return

    import httpx

    real_sync = httpx.HTTPTransport.handle_request
    real_async = httpx.AsyncHTTPTransport.handle_async_request

    def _refuse(host):
        return httpx.ConnectError(
            f"outbound network is disabled in tests (host {host!r}). Stub the "
            f"fetcher, or mark the test @pytest.mark.network if it must call out."
        )

    def _sync(self, req, *a, **k):
        if req.url.host not in _LOCAL_HOSTS:
            raise _refuse(req.url.host)
        return real_sync(self, req, *a, **k)

    async def _async(self, req, *a, **k):
        if req.url.host not in _LOCAL_HOSTS:
            raise _refuse(req.url.host)
        return await real_async(self, req, *a, **k)

    import requests.adapters as _ra
    import requests.exceptions as _re
    from urllib.parse import urlparse

    real_send = _ra.HTTPAdapter.send

    def _send(self, req, *a, **k):
        host = urlparse(req.url).hostname or ""
        if host not in _LOCAL_HOSTS:
            raise _re.ConnectionError(
                f"outbound network is disabled in tests (host {host!r})"
            )
        return real_send(self, req, *a, **k)

    httpx.HTTPTransport.handle_request = _sync
    httpx.AsyncHTTPTransport.handle_async_request = _async
    _ra.HTTPAdapter.send = _send
    try:
        yield
    finally:
        httpx.HTTPTransport.handle_request = real_sync
        httpx.AsyncHTTPTransport.handle_async_request = real_async
        _ra.HTTPAdapter.send = real_send


# ── imports ─────────────────────────────────────────────────────────────
try:
    from database import get_db
    from main import app
    from models import Base
except ModuleNotFoundError:
    from backend.database import get_db
    from backend.main import app
    from backend.models import Base

# ── SQLite test engine ──────────────────────────────────────────────────
SQLALCHEMY_DATABASE_URL = "sqlite://"  # in-memory

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)


# Enable WAL/foreign-key support for consistency
@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):  # noqa: ARG001
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _setup_tables():
    """Create all tables before each test, drop them after."""
    # Clear in-memory endpoint caches so stale responses from previous
    # tests (which may have had different seed data) don't leak through.
    from main import clear_all_caches
    clear_all_caches()

    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db_session():
    """Provide a transactional DB session that rolls back after each test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db_session):
    """FastAPI TestClient with the DB dependency overridden to use test session."""

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass  # session cleanup handled by db_session fixture

    app.dependency_overrides[get_db] = _override_get_db

    # Prevent startup events (bootstrap_reference_data, auto-seeder) from
    # hitting the real PostgreSQL database – they are irrelevant for unit
    # tests and will fail in CI where PG tables haven't been migrated.
    _saved_startup = list(app.router.on_startup)
    _saved_shutdown = list(app.router.on_shutdown)
    app.router.on_startup.clear()
    app.router.on_shutdown.clear()

    # Many routes call `next(get_db())` directly instead of using FastAPI
    # Depends – this bypasses dependency_overrides.  Monkey-patch the
    # module-level `get_db` in **main** so those code paths also use the
    # test SQLite session.
    #
    # The rate limiter is bypassed session-wide in pytest_configure above —
    # patching it here would be a no-op (the middleware instance binds
    # dispatch_func at construction, before this fixture ever runs).
    with patch("main.get_db", _override_get_db):
        yield TestClient(app, raise_server_exceptions=False)

    # Restore handlers so subsequent test parametrisations still work
    app.router.on_startup = _saved_startup
    app.router.on_shutdown = _saved_shutdown
    app.dependency_overrides.clear()


# ── seed helpers (import into individual test files as needed) ──────────
@pytest.fixture()
def seed_country(db_session):
    """Insert a minimal Kenya Country row and return it."""
    from models import Country

    country = Country(
        id=1,
        iso_code="KEN",
        name="Kenya",
        currency="KES",
        timezone="Africa/Nairobi",
        default_locale="en_KE",
    )
    db_session.add(country)
    db_session.commit()
    db_session.refresh(country)
    return country


@pytest.fixture()
def seed_entity(db_session, seed_country):
    """Insert a sample county entity and return it."""
    from models import Entity, EntityType

    entity = Entity(
        id=1,
        country_id=seed_country.id,
        type=EntityType.COUNTY,
        canonical_name="Nairobi",
        slug="nairobi",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity


@pytest.fixture()
def seed_fiscal_period(db_session, seed_country):
    """Insert a fiscal period and return it."""
    from models import FiscalPeriod

    fp = FiscalPeriod(
        id=1,
        country_id=seed_country.id,
        label="FY2024/25",
        start_date=datetime(2024, 7, 1),
        end_date=datetime(2025, 6, 30),
    )
    db_session.add(fp)
    db_session.commit()
    db_session.refresh(fp)
    return fp


@pytest.fixture()
def seed_source_doc(db_session, seed_country):
    """Insert a source document and return it."""
    from models import DocumentStatus, DocumentType, SourceDocument

    doc = SourceDocument(
        id=1,
        country_id=seed_country.id,
        publisher="Kenya National Treasury",
        title="FY2024/25 Budget Estimates",
        url="https://treasury.go.ke/budget-2024",
        fetch_date=datetime(2024, 8, 1, tzinfo=timezone.utc),
        doc_type=DocumentType.BUDGET,
        status=DocumentStatus.AVAILABLE,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc
