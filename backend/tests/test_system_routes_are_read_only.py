"""Nobody on the internet may start a seed.

``POST /api/v1/system/seeder-refresh`` took no credentials and ran
``asyncio.create_task(auto_seeder.seed_all_domains())``: a full in-app seed
that writes counties, the national entity, population and economic rows. In
production the auto-seeder is running, so the handler's only guard
(``is_running``) passed and any anonymous POST got 200. Nothing in the repo
called it; the nightly seed runs from GitHub Actions and an admin-gated
trigger already exists at ``POST /api/v1/admin/etl/trigger/{source}``. The
route is removed.

THE RULE. ``/api/v1/system/*`` is a read-only namespace: status pages read
it, nothing writes through it. A route there that accepts anything but
GET/HEAD fails ``test_system_namespace_registers_only_reads``. If a write
route is ever needed here, put it behind ``require_admin`` (or the signed
scheme in ``routers/cache_invalidation.py`` once that lands) and change this
test to check for that dependency; do not widen the method set.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, FastAPI

from main import app

SYSTEM_PREFIX = "/api/v1/system/"
READ_METHODS = {"GET", "HEAD"}


def test_anonymous_post_cannot_start_a_seed(client):
    """The defect itself: an unauthenticated POST must not reach the seeder."""
    from services.auto_seeder import auto_seeder

    seed = AsyncMock()
    # is_running=True is the production state (GET /api/v1/system/seeder-status
    # reports it), and it is the only condition the old handler checked.
    with patch.object(auto_seeder, "is_running", True), patch.object(
        auto_seeder, "seed_all_domains", seed
    ):
        response = client.post("/api/v1/system/seeder-refresh")

    assert not 200 <= response.status_code < 300, (
        f"anonymous POST /api/v1/system/seeder-refresh returned "
        f"{response.status_code}: {response.text[:200]}"
    )
    assert seed.call_count == 0, "an anonymous POST started seed_all_domains()"


def _served_routes(application):
    """(path, methods) for every route FastAPI serves, including routers.

    ``app.routes`` alone is not enough: on this FastAPI (0.139) an included
    router is one wrapper entry, so a write route added under the system
    prefix through ``include_router`` never appears there. ``iter_route_contexts``
    is what ``app.openapi()`` walks. If a future FastAPI drops it, fail rather
    than quietly scan only ``main.py``'s own routes.
    """
    try:
        from fastapi.routing import iter_route_contexts
    except ImportError as exc:  # pragma: no cover - depends on FastAPI version
        raise AssertionError(
            "fastapi.routing.iter_route_contexts is gone; this guard cannot see "
            "routes mounted through routers"
        ) from exc
    return [
        (ctx.path, set(ctx.methods or ()))
        for ctx in iter_route_contexts(application.routes)
        if getattr(ctx, "path", None) is not None
    ]


def _system_writers(application):
    return sorted(
        f"{sorted(methods - READ_METHODS)} {path}"
        for path, methods in _served_routes(application)
        if path.startswith(SYSTEM_PREFIX) and methods - READ_METHODS
    )


def test_system_namespace_registers_only_reads():
    system_paths = {
        path for path, _m in _served_routes(app) if path.startswith(SYSTEM_PREFIX)
    }
    # Not vacuous: the status routes the frontend reads must still be here.
    assert system_paths >= {
        "/api/v1/system/seeder-status",
        "/api/v1/system/pipeline-health",
    }
    writers = _system_writers(app)
    assert writers == [], f"write routes under {SYSTEM_PREFIX}: {writers}"


def test_the_guard_sees_a_write_route_mounted_through_a_router():
    """Positive control: the shape the first version of this test missed."""
    probe = FastAPI()
    router = APIRouter(prefix="/api/v1/system")

    @router.post("/reseed")
    def _reseed():  # pragma: no cover - never called
        return {}

    probe.include_router(router)
    assert _system_writers(probe) == ["['POST'] /api/v1/system/reseed"]
