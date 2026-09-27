"""Nobody on the internet may start ETL work through ``main.py`` (#252).

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

THE RULE (``test_every_main_write_route_verifies_the_caller``). Every route
defined in ``main.py`` that accepts a method other than GET/HEAD must depend on
one of ``AUTH_DEPENDENCIES`` (which verify a Supabase token), or be listed in
``PUBLIC_WRITE_ROUTES`` with the reason it is safe to leave open. ``HTTPBearer``
alone does not count. Routes in ``backend/routers/`` are not scanned here.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.routing import APIRoute

import main
import supabase_auth
from main import app

READ_METHODS = {"GET", "HEAD"}

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
}

# Write routes that another open PR removes. Tolerated while present, not
# required, so this test stays green whichever PR merges first. Delete the
# entry once the route is gone from main.
REMOVED_BY_OPEN_PR = {
    ("POST", "/api/v1/system/seeder-refresh"): "PR #253 (issue #252)",
}


def _main_write_routes() -> list[tuple[str, str, APIRoute]]:
    out = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.endpoint.__module__ != main.__name__:
            continue
        for method in sorted(route.methods - READ_METHODS):
            out.append((method, route.path, route))
    return out


def _dependency_calls(dependant) -> list:
    calls = []
    for sub in dependant.dependencies:
        calls.append(sub.call)
        calls.extend(_dependency_calls(sub))
    return calls


def test_every_main_write_route_verifies_the_caller():
    routes = _main_write_routes()
    keys = {(m, p) for m, p, _ in routes}

    # Not vacuous: the scan must see main.py's write routes, including one
    # that is gated and one that is allowlisted.
    assert ("POST", "/api/v1/admin/etl/run") in keys
    assert ("POST", "/api/v1/annotations") in keys
    assert ("OPTIONS", "/api/v1/counties") in keys

    open_routes = sorted(
        f"{method} {path}"
        for method, path, route in routes
        if (method, path) not in PUBLIC_WRITE_ROUTES
        and (method, path) not in REMOVED_BY_OPEN_PR
        and not AUTH_DEPENDENCIES.intersection(_dependency_calls(route.dependant))
    )
    assert open_routes == [], (
        "write routes in main.py with no verified-auth dependency "
        f"(add Depends(require_admin), or allowlist with a reason): {open_routes}"
    )


def test_public_write_allowlist_has_no_stale_entries():
    keys = {(m, p) for m, p, _ in _main_write_routes()}
    stale = sorted(f"{m} {p}" for m, p in PUBLIC_WRITE_ROUTES if (m, p) not in keys)
    assert stale == [], f"PUBLIC_WRITE_ROUTES lists routes that no longer exist: {stale}"


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
    assert pipeline_cls.call_count == 0, f"anonymous POST {path} built a KenyaDataPipeline"
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
