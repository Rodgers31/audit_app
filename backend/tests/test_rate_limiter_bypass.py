"""The rate limiter must be inert for the test harness — and only for it.

Background
----------
Every request a Starlette ``TestClient`` makes reports the same client IP
("testclient"), so the whole suite shares ONE 120-request/60-second window in
the mounted ``RateLimitMiddleware``.  A full run makes >1000 requests, so the
limiter trips partway through and turns a large, *wall-clock dependent* slice
of the suite red — the failure count differed on every run of identical code.

The bypass lives in ``conftest.pytest_configure`` because it has to be
installed before the middleware stack is built: Starlette's
``BaseHTTPMiddleware`` binds ``self.dispatch_func = self.dispatch`` in
``__init__``, so a per-test ``patch()`` of the class attribute arrives too late
and does nothing.

These two tests are the positive control for that bypass.  The first fails if
the bypass stops working; the second fails if the bypass is over-broad and has
neutered the production limiter as well.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.security import RateLimitMiddleware

# The mounted limiter's production budget (main.py: calls=120, period=60).
MOUNTED_CALLS = 120


def test_test_harness_is_never_rate_limited(client):
    """More requests than the production window allows, none refused.

    Remove the bypass in conftest and this goes red at request 121.
    """
    statuses = {client.get("/health/live").status_code for _ in range(MOUNTED_CALLS + 10)}
    assert statuses == {200}, f"rate limiter is live in the test harness: saw {sorted(statuses)}"


def test_production_rate_limiter_still_refuses_over_the_limit():
    """The bypass must not have deleted the real limiter's behaviour.

    Mounts the *original* dispatch (stashed by conftest before it was swapped
    out) on a throwaway app and drives it past a deliberately tiny budget.
    """
    original = getattr(RateLimitMiddleware, "_original_dispatch", None)
    assert original is not None, "conftest did not stash the real dispatch"

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(RateLimitMiddleware, "dispatch", original)

        app = FastAPI()

        @app.get("/x")
        def _x():  # pragma: no cover - trivial
            return {"ok": True}

        # Instantiated on the first request below, i.e. inside this context,
        # so dispatch_func binds to the real implementation.
        app.add_middleware(RateLimitMiddleware, calls=3, period=60)
        c = TestClient(app, raise_server_exceptions=False)

        assert [c.get("/x").status_code for _ in range(3)] == [200, 200, 200]

        refused = c.get("/x")
        assert refused.status_code == 429, (
            "over-limit request was not refused with 429 — if this is a 500 the "
            "limiter is raising HTTPException from dispatch again, which runs "
            "outside Starlette's ExceptionMiddleware"
        )
        assert refused.headers.get("retry-after") == "60"
