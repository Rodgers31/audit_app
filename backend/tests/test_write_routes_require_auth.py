"""Nobody on the internet may write through the API without being verified (#252).

Four write routes defined directly on ``app`` in ``main.py`` started ETL work
without verifying who asked:

* ``POST /api/v1/etl/treasury/run-batch`` and ``POST /api/v1/etl/cob/run-batch``
  took no credentials and ran ``KenyaDataPipeline`` download batches.
* ``POST /api/v1/etl/kenya/start`` took no credentials and scheduled
  ``etl_test_runner.SimpleKenyaETL().run_full_pipeline()``.
* ``POST /api/v1/admin/etl/run`` looked gated, but its only dependency was a
  bare ``HTTPBearer()``. That checks an ``Authorization: Bearer <anything>``
  header is present and never verifies it, so ``Bearer x`` started a job.

Nothing in the repo called the first three, so they were removed. The fourth
is now behind ``require_admin``, like the rest of ``/admin``.

THE RULE (``test_every_write_route_verifies_the_caller``). Every route mounted
on ``app`` (``main.py`` and every router in ``backend/routers/``) that accepts
a method other than GET/HEAD must have one of ``AUTH_DEPENDENCIES`` in the
dependency tree FastAPI runs for it, or be listed in ``PUBLIC_WRITE_ROUTES``
with the reason it is safe to leave open. ``HTTPBearer`` alone does not count.

Router dependencies are checked as mounted: ``APIRouter(dependencies=...)`` and
``include_router(..., dependencies=...)`` both count, because the scan reads
the effective route FastAPI builds when it includes a router.

``main.py`` includes every router inside ``try/except Exception``, so a router
that fails to import is silently left out of ``app``, and out of any scan of
``app``. ``test_every_router_write_route_is_mounted`` imports each module in
``backend/routers/`` itself and fails if one of its write routes is not on
``app``.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute, APIRouter

import main
import supabase_auth
from main import app

try:
    # FastAPI >= 0.13x keeps an included router as one ``_IncludedRouter``
    # entry in ``app.routes``. This is the flattening ``app.openapi()`` uses;
    # it yields each route with its prefixed path and merged dependencies.
    from fastapi.routing import iter_route_contexts
except ImportError:  # older FastAPI copies included routes into app.routes
    iter_route_contexts = None

READ_METHODS = {"GET", "HEAD"}
ROUTERS_DIR = Path(__file__).resolve().parent.parent / "routers"

# Dependencies that verify the caller's Supabase JWT (and, for require_admin,
# the admin role). A route passes the rule only if one of these is somewhere in
# its dependency tree.
AUTH_DEPENDENCIES = {
    supabase_auth.require_admin,
    supabase_auth.get_current_user,
    supabase_auth.get_current_db_user,
}

# (method, path) -> why it is safe for an anonymous caller.
PUBLIC_WRITE_ROUTES = {
    ("OPTIONS", "/api/v1/counties"): (
        "CORS probe: returns an empty 204 and does no work."
    ),
    ("POST", "/api/v1/newsletter/subscribe"): (
        "Newsletter sign-up needs no account by design (NewsletterBanner). "
        "Creates at most one subscriber and welcome email per normalized address; signed proof is required to reverse an opt-out."
    ),
    ("POST", "/api/v1/newsletter/unsubscribe-verify"): (
        "Called from the emailed unsubscribe link; the handler 403s unless "
        "verify_unsubscribe_token(email, token) passes."
    ),
}

# Open to anonymous callers, and NOT safe. Tolerated so this test can land
# without a product change; each needs a decision, then removal from here.
KNOWN_UNGATED_WRITE_ROUTES: dict = {}

# Write routes that authenticate the CALLER by a request signature instead of
# a user session. Tolerated while absent (the cache-invalidation route lands
# with the freshness PR, #231), and while present
# test_signed_write_routes_refuse_an_unsigned_request proves the handler turns
# away anyone without the signature before it does any work.
SIGNED_WRITE_ROUTES = {
    ("POST", "/api/v1/system/cache/status"): (
        "Worker cache observation uses the same HMAC-SHA256 signature and "
        "freshness check as invalidate; observation is refused before "
        "generation_status when the caller is unsigned or the secret is unset."
    ),
    ("POST", "/api/v1/system/cache/invalidate"): (
        "Called by the nightly seed after seed+validate. HMAC-SHA256 of the raw "
        "body with REVALIDATE_SECRET in x-revalidate-signature, and a ts within "
        "300s; 503 when the secret is unset (routers/cache_invalidation.py)."
    ),
}

# Write routes that another open PR removes. Tolerated while present, not
# required, so this test stays green whichever PR merges first. Delete the
# entry once the route is gone from main. Empty since #253 and this change
# merged together: POST /api/v1/system/seeder-refresh no longer exists, and
# test_system_routes_are_read_only.py refuses any write route under /system.
REMOVED_BY_OPEN_PR: dict = {}


def _mounted_write_routes(application=app) -> list[tuple[str, str, object, object]]:
    """Every effective write surface, including mounts and WebSockets.

    A Starlette route without a FastAPI dependant remains visible and ungated;
    an opaque mount requires an explicit, behavior-proven exception.
    """
    from starlette.routing import Mount, Route, WebSocketRoute

    def walk(routes, prefix=""):
        contexts = (
            iter_route_contexts(routes) if iter_route_contexts is not None else routes
        )
        for ctx in contexts:
            route = getattr(ctx, "route", ctx)
            path = prefix + getattr(ctx, "path", getattr(route, "path", ""))
            if isinstance(route, Mount):
                children = getattr(route.app, "routes", None)
                if children is None:
                    yield ("ANY", path + "/{path:path}", route.app, None)
                else:
                    yield from walk(children, path)
                continue
            dependant = getattr(ctx, "dependant", getattr(route, "dependant", None))
            endpoint = getattr(ctx, "endpoint", getattr(route, "endpoint", None))
            methods = getattr(ctx, "methods", getattr(route, "methods", None))
            if methods is None:
                methods = {"ANY"} if isinstance(route, Route) else set()
            if isinstance(route, WebSocketRoute):
                methods = {"WEBSOCKET"}
            for method in sorted(set(methods) - READ_METHODS):
                yield (method, path, endpoint, dependant)

    return list(walk(application.routes))


def _dependency_calls(dependant) -> list:
    calls = []
    for sub in getattr(dependant, "dependencies", ()):
        calls.append(sub.call)
        calls.extend(_dependency_calls(sub))
    return calls


def test_every_write_route_verifies_the_caller():
    routes = _mounted_write_routes()
    keys = {(m, p) for m, p, _, _ in routes}

    # Not vacuous: the scan must see write routes from main.py and from
    # routers, gated by a route dependency, by APIRouter(dependencies=...),
    # and allowlisted.
    assert ("POST", "/api/v1/admin/etl/run") in keys  # main.py, route dep
    assert ("POST", "/api/v1/annotations") in keys  # main.py, get_current_db_user
    assert ("POST", "/api/v1/admin/etl/trigger/{source}") in keys  # router-level
    assert ("DELETE", "/api/v1/admin/users/{user_id}") in keys  # router-level
    assert ("POST", "/api/v1/user/watchlist") in keys  # router, route dep
    assert ("POST", "/api/v1/newsletter/subscribe") in keys  # allowlisted
    assert ("POST", "/api/v1/system/cache/status") in keys  # signed caller

    open_routes = sorted(
        f"{method} {path}"
        for method, path, _, dependant in routes
        if (method, path) not in PUBLIC_WRITE_ROUTES
        and (method, path) not in KNOWN_UNGATED_WRITE_ROUTES
        and (method, path) not in REMOVED_BY_OPEN_PR
        and (method, path) not in SIGNED_WRITE_ROUTES
        and not AUTH_DEPENDENCIES.intersection(_dependency_calls(dependant))
    )
    assert open_routes == [], (
        "write routes with no verified-auth dependency "
        f"(add Depends(require_admin), or allowlist with a reason): {open_routes}"
    )


def test_router_level_dependencies_are_seen():
    """The scan reads the dependencies FastAPI runs, not the handler signature.

    Every real router write route also names its gate in the handler, so this
    builds routers whose handlers take nothing: one gated by
    ``APIRouter(dependencies=...)``, one by ``include_router(dependencies=...)``,
    and one left open.
    """
    from fastapi import Depends, FastAPI

    router_gated = APIRouter(dependencies=[Depends(supabase_auth.require_admin)])
    include_gated = APIRouter()
    ungated = APIRouter()

    @router_gated.post("/a")
    def a():
        return {}

    @include_gated.post("/b")
    def b():
        return {}

    @ungated.post("/c")
    def c():
        return {}

    probe = FastAPI()
    probe.include_router(router_gated, prefix="/p")
    probe.include_router(
        include_gated, prefix="/p", dependencies=[Depends(supabase_auth.require_admin)]
    )
    probe.include_router(ungated, prefix="/p")

    gated = {
        path: bool(AUTH_DEPENDENCIES.intersection(_dependency_calls(dep)))
        for _, path, _, dep in _mounted_write_routes(probe)
    }
    assert gated == {"/p/a": True, "/p/b": True, "/p/c": False}


def _router_modules() -> list[str]:
    return sorted(
        f"routers.{m.name}"
        for m in pkgutil.iter_modules([str(ROUTERS_DIR)])
        if not m.name.startswith("_")
    )


def test_every_router_write_route_is_mounted():
    modules = _router_modules()
    assert "routers.etl_admin" in modules and "routers.user_features" in modules

    mounted = {endpoint for _, _, endpoint, _ in _mounted_write_routes()}
    unmounted = []
    for name in modules:
        module = importlib.import_module(name)  # an import error fails the test
        for router in vars(module).values():
            if not isinstance(router, APIRouter):
                continue
            for route in router.routes:
                if not isinstance(route, APIRoute):
                    continue
                if route.methods - READ_METHODS and route.endpoint not in mounted:
                    unmounted.append(f"{name}: {sorted(route.methods)} {route.path}")
    assert unmounted == [], (
        "write routes defined in backend/routers/ but not mounted on app, so the "
        f"auth rule cannot see them (did the include in main.py fail?): {unmounted}"
    )


def test_write_allowlists_have_no_stale_entries():
    keys = {(m, p) for m, p, _, _ in _mounted_write_routes()}
    stale = sorted(
        f"{m} {p}"
        for m, p in [*PUBLIC_WRITE_ROUTES, *KNOWN_UNGATED_WRITE_ROUTES]
        if (m, p) not in keys
    )
    assert stale == [], f"allowlists name routes that no longer exist: {stale}"


def _fake_pipeline_modules():
    """Stand-ins for repo-root ``etl/kenya_pipeline`` and ``etl_test_runner``.

    The old handlers imported these by name; with fakes in ``sys.modules`` a
    handler that is reached records a construction instead of fetching.
    """
    kenya_pipeline = types.ModuleType("kenya_pipeline")
    pipeline_cls = MagicMock(name="KenyaDataPipeline")
    pipeline_cls.return_value.discover_budget_documents.return_value = []
    kenya_pipeline.KenyaDataPipeline = pipeline_cls

    etl_test_runner = types.ModuleType("etl_test_runner")
    runner_cls = MagicMock(name="SimpleKenyaETL")
    runner_cls.return_value.run_full_pipeline.return_value = {
        "sources_accessible": 0,
        "entities_extracted": 0,
        "documents_processed": 0,
    }
    etl_test_runner.SimpleKenyaETL = runner_cls

    modules = {
        "kenya_pipeline": kenya_pipeline,
        "etl.kenya_pipeline": kenya_pipeline,
        "etl_test_runner": etl_test_runner,
    }
    return modules, pipeline_cls, runner_cls


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/etl/treasury/run-batch",
        "/api/v1/etl/cob/run-batch",
        "/api/v1/etl/kenya/start",
    ],
)
def test_anonymous_post_cannot_start_etl(client, path):
    modules, pipeline_cls, runner_cls = _fake_pipeline_modules()
    with patch.dict(sys.modules, modules):
        response = client.post(path)

    assert not 200 <= response.status_code < 300, (
        f"anonymous POST {path} returned {response.status_code}: "
        f"{response.text[:200]}"
    )
    assert (
        pipeline_cls.call_count == 0
    ), f"anonymous POST {path} built a KenyaDataPipeline"
    assert runner_cls.call_count == 0, f"anonymous POST {path} ran SimpleKenyaETL"


def test_unverified_bearer_cannot_start_admin_etl_run(client):
    run_job = AsyncMock(return_value={})
    jobs_before = dict(main._etl_jobs)
    with patch.object(main, "_run_job", run_job):
        response = client.post(
            "/api/v1/admin/etl/run",
            params={"source": "cob", "job": "light"},
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code in (401, 403), (
        f"POST /api/v1/admin/etl/run with an unverified bearer returned "
        f"{response.status_code}: {response.text[:200]}"
    )
    # The handler records the job before scheduling it, so a new key means
    # it was reached even if the background task never ran.
    assert main._etl_jobs == jobs_before, "the handler queued an ETL job"
    assert run_job.await_count == 0


@pytest.mark.parametrize("method, path", sorted(SIGNED_WRITE_ROUTES))
def test_signed_write_routes_refuse_an_unsigned_request(
    client, monkeypatch, method, path
):
    """A signed route is exempt from the session rule only if it checks the signature."""
    if (method, path) not in {(m, p) for m, p, _, _ in _mounted_write_routes()}:
        pytest.skip(f"{method} {path} is not mounted on this tree")
    import importlib

    handler_module = importlib.import_module("routers.cache_invalidation")
    ran = []
    monkeypatch.setattr(
        handler_module, "invalidate_all", lambda *a, **k: ran.append(1) or {}
    )
    monkeypatch.setattr(
        handler_module, "generation_status", lambda: ran.append("status") or {}
    )

    # A FRESH timestamp, so the only thing that can refuse these is the
    # signature check. (A stale ts is refused by the replay check too, which
    # would let this test pass with the signature check removed.)
    import json
    import time

    body = json.dumps({"ts": int(time.time()), "reason": "probe"}).encode()

    # Secret configured: no signature, and a wrong one, are both refused.
    monkeypatch.setenv("REVALIDATE_SECRET", "test-secret-not-a-real-one")
    unsigned = client.request(method, path, content=body)
    wrong = client.request(
        method, path, content=body, headers={"x-revalidate-signature": "0" * 64}
    )
    # Secret unset: the endpoint is disabled rather than open.
    monkeypatch.delenv("REVALIDATE_SECRET")
    disabled = client.request(method, path, content=body)

    for response in (unsigned, wrong):
        assert response.status_code == 401, response.text
        assert response.json()["detail"]["error"] == "invalid_signature", response.text
    assert disabled.status_code == 503, disabled.text
    assert (
        disabled.json()["detail"]["error"] == "invalidation_not_configured"
    ), disabled.text
    assert ran == [], "an unsigned request reached cache invalidation or observation"
