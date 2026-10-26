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
with the reason it is safe to leave open, or in an exact signature/capability
exception family whose mounted behavior is tested below. ``HTTPBearer`` alone
does not count.

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

# Provider signatures are independent of the worker cache-invalidation secret.
# The mounted HTTP rejection controls below keep this exemption behavioral.
PROVIDER_SIGNED_WRITE_ROUTES = {
    ("POST", "/api/v1/social/platform-events/{provider}"): (
        "Threads/TikTok require an enabled exact-provider composition and a "
        "signature over bounded raw bytes before parsing or persistence."
    ),
}

# A top-level OAuth launch uses an administrator-created one-use capability,
# not a browser bearer relay. Only this exact mounted route has that contract.
CAPABILITY_WRITE_ROUTES = {
    ("POST", "/api/v1/social/oauth/meta/launch"): (
        "An authenticated administrator creates the flow; launch requires its "
        "one-use capability, exact origin/target and bounded form input. "
        "It sets only browser binding; completion still verifies the initiating session."
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
    assert ("POST", "/api/v1/social/oauth/meta/launch") in keys  # one-use capability

    open_routes = sorted(
        f"{method} {path}"
        for method, path, _, dependant in routes
        if (method, path) not in PUBLIC_WRITE_ROUTES
        and (method, path) not in KNOWN_UNGATED_WRITE_ROUTES
        and (method, path) not in REMOVED_BY_OPEN_PR
        and (method, path) not in SIGNED_WRITE_ROUTES
        and (method, path) not in PROVIDER_SIGNED_WRITE_ROUTES
        and (method, path) not in CAPABILITY_WRITE_ROUTES
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
        for m, p in [*PUBLIC_WRITE_ROUTES, *KNOWN_UNGATED_WRITE_ROUTES,
                     *PROVIDER_SIGNED_WRITE_ROUTES, *CAPABILITY_WRITE_ROUTES]
        if (m, p) not in keys
    )
    assert stale == [], f"allowlists name routes that no longer exist: {stale}"


@pytest.mark.parametrize('provider', ['threads', 'tiktok'])
def test_provider_signed_route_refuses_before_persistence(client, monkeypatch, provider):
    from social import platform_events

    config = platform_events.EventConfig(
        provider, enabled=True, subscription_verified=True, product_access_verified=True,
        app_id='fixture-app', app_secret='inert-fixture-signing-key',
        verify_token='inert-fixture-verify', subscriptions=(('fixture-sub', 'fixture-account'),),
        account_ids=('fixture-account',),
    )
    monkeypatch.setattr(client.app.state, 'social_platform_events_config',
                        {provider: config}, raising=False)
    ran = []
    monkeypatch.setattr(platform_events, 'accept_event', lambda *a, **k: ran.append(1))
    path = f'/api/v1/social/platform-events/{provider}'
    header = 'x-hub-signature-256' if provider == 'threads' else 'tiktok-signature'
    for headers in ({}, {header: 'invalid'}):
        response = client.post(path, content=b'{"fixture":true}',
                               headers={'content-type': 'application/json', **headers})
        assert response.status_code == 403, response.text
        assert response.json()['detail']['code'] == 'PROVIDER_SIGNATURE_INVALID'
    monkeypatch.setattr(client.app.state, 'social_platform_events_config', {})
    response = client.post(path, content=b'{"fixture":true}')
    assert response.status_code == 503, response.text
    assert ran == []


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


_META_ORIGIN = 'https://admin.example.test'
_META_API = 'https://api.example.test'
_META_LAUNCH = '/api/v1/social/oauth/meta/launch'
_META_CALLBACK = _META_API + '/api/v1/social/oauth/meta/callback'
_META_ADMIN = '/api/v1/admin/social/connections/meta/direct'


def _meta_launch_config():
    from cryptography.fernet import Fernet
    from social.connections.config import MetaConfig

    return MetaConfig(
        enabled=True, app_configuration_validated=True,
        app_id='810', app_secret='inert-mounted-launch-fixture',
        access_mode='owned_standard', active_key_version='fixture',
        encryption_keys={'fixture': Fernet.generate_key().decode()},
        direct_callback_enabled=True, admin_origin=_META_ORIGIN,
        redirect_uris=(_META_CALLBACK,),
        verified_callback_ingress_uris=(_META_CALLBACK,),
    )


def _assert_real_meta_launch_is_mounted():
    from social.connections.direct_api import launch

    matches = [(endpoint, dep) for method, path, endpoint, dep in _mounted_write_routes()
               if (method, path) == ('POST', _META_LAUNCH)]
    assert len(matches) == 1 and matches[0][0] is launch


@pytest.mark.parametrize('case', [
    'disabled', 'unqualified', 'empty', 'missing_token', 'invalid_uuid',
    'duplicate_token', 'extra_field', 'oversized', 'wrong_content_type',
    'query', 'wrong_target', 'missing_origin', 'wrong_origin',
    'malformed_token', 'unknown_flow',
])
def test_meta_launch_capability_route_refuses_before_mutation_or_provider(
    client, monkeypatch, case,
):
    """The mounted handler checks the capability, not just its presence."""
    from contextlib import contextmanager
    from dataclasses import replace
    from urllib.parse import urlencode
    from social.connections.api import service
    from social.connections.service import ConnectionService

    class NoPersistence:
        def __init__(self):
            self.reads = 0
            self.write_attempts = []

        @contextmanager
        def begin(self):
            yield

        def scalar(self, statement):
            self.reads += 1
            return None  # A well-formed capability still needs a stored flow.

        def __getattr__(self, name):
            self.write_attempts.append(name)
            raise AssertionError('Refused launch touched persistence: ' + name)

    _assert_real_meta_launch_is_mounted()
    db, provider_calls = NoPersistence(), []
    config = _meta_launch_config()
    if case == 'disabled':
        config = replace(config, direct_callback_enabled=False)
    if case == 'unqualified':
        config = replace(config, verified_callback_ingress_uris=())

    def provider(*args):
        provider_calls.append(1)
        raise AssertionError('Refused launch reached the provider')

    monkeypatch.setitem(client.app.dependency_overrides, service,
                        lambda: ConnectionService(db, config, provider_factory=provider))
    fields = {'flow_id': '00000000-0000-4000-8000-000000000810',
              'launch_token': 'n' * 43}
    body = urlencode(fields)
    path = _META_API + _META_LAUNCH
    headers = {'Origin': _META_ORIGIN,
               'Content-Type': 'application/x-www-form-urlencoded'}
    status, code = 409, 'OAUTH_CALLBACK_INVALID'
    if case in {'disabled', 'unqualified'}:
        status, code = 503, 'CALLBACK_INGRESS_UNVERIFIED'
    elif case == 'empty':
        body = ''
    elif case == 'missing_token':
        body = urlencode({'flow_id': fields['flow_id']})
    elif case == 'invalid_uuid':
        body = urlencode({**fields, 'flow_id': 'not-a-uuid'})
    elif case == 'duplicate_token':
        body += '&%6caunch_token=other'
    elif case == 'extra_field':
        body += '&code=INERT'
    elif case == 'oversized':
        body = 'x' * 1025
    elif case == 'wrong_content_type':
        headers['Content-Type'] = 'application/json'
    elif case == 'query':
        path += '?launch_token=INERT'
    elif case == 'wrong_target':
        path = path.replace('api.example.test', 'different.example.test')
        status, code = 422, 'REDIRECT_MISMATCH'
    elif case in {'missing_origin', 'wrong_origin', 'malformed_token'}:
        code = 'OAUTH_ORIGIN_INVALID'
        if case == 'missing_origin':
            headers.pop('Origin')
        elif case == 'wrong_origin':
            headers['Origin'] = 'https://different.example.test'
        else:
            body = urlencode({**fields, 'launch_token': 'invalid'})

    response = client.post(path, content=body, headers=headers, follow_redirects=False)
    assert response.status_code == status, response.text
    assert response.json()['detail']['code'] == code
    assert 'location' not in response.headers and 'set-cookie' not in response.headers
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert db.reads == (1 if case == 'unknown_flow' else 0)
    assert db.write_attempts == [] and provider_calls == []


def test_mounted_meta_launch_is_one_use_and_completion_keeps_session_auth(client, monkeypatch):
    """The exception cannot authorize creation, completion or account mutation."""
    from urllib.parse import parse_qs, urlsplit
    from uuid import uuid4
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool
    from social.connections.api import service
    from social.connections.models import SocialOAuthFlow
    from social.connections.service import ConnectionService
    from social.models import Base, SOCIAL_TABLES, SocialAccount, SocialPublication

    _assert_real_meta_launch_is_mounted()
    engine = create_engine('sqlite://', poolclass=StaticPool,
                           connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine, tables=SOCIAL_TABLES)
    config, provider_calls = _meta_launch_config(), []

    class InertProvider:
        def discover(self, code, redirect):
            provider_calls.append((code, redirect))
            return {'choices': [], 'metadata': {'scopes': []}}

        def close(self):
            pass

    def isolated_service():
        with Session(engine, expire_on_commit=False) as db:
            yield ConnectionService(db, config, provider_factory=lambda _: InertProvider())

    monkeypatch.setitem(client.app.dependency_overrides, service, isolated_service)
    actor, session_id = str(uuid4()), str(uuid4())
    principal = {'value': types.SimpleNamespace(id=actor, roles=['admin'], session_id=session_id)}
    admin = lambda: principal['value']
    command_headers = {'Origin': _META_ORIGIN, 'Idempotency-Key': str(uuid4())}
    start_body = {'admin_origin': _META_ORIGIN, 'reason': 'Inert mounted capability control'}
    try:
        denied = client.post(_META_API + _META_ADMIN + '/start', json=start_body,
                             headers=command_headers)
        assert denied.status_code in {401, 403}, denied.text
        monkeypatch.setitem(client.app.dependency_overrides, supabase_auth.require_admin, admin)
        started = client.post(_META_API + _META_ADMIN + '/start', json=start_body,
                              headers=command_headers)
        assert started.status_code == 200, started.text
        flow = started.json()
        form = {'flow_id': flow['flow_id'], 'launch_token': flow['launch_token']}
        wrong = client.post(flow['launch_url'], data={**form, 'launch_token': 'b' * 43},
                            headers={'Origin': _META_ORIGIN}, follow_redirects=False)
        assert wrong.status_code == 409 and wrong.json()['detail']['code'] == 'OAUTH_STATE_USED'
        launched = client.post(flow['launch_url'], data=form,
                               headers={'Origin': _META_ORIGIN}, follow_redirects=False)
        assert launched.status_code == 303, launched.text
        provider_url = urlsplit(launched.headers['location'])
        assert provider_url.scheme == 'https' and provider_url.netloc == 'www.facebook.com'
        cookie = launched.headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=lax' in cookie
        assert 'Domain=' not in cookie
        replay = client.post(flow['launch_url'], data=form,
                             headers={'Origin': _META_ORIGIN}, follow_redirects=False)
        assert replay.status_code == 409 and replay.json()['detail']['code'] == 'OAUTH_STATE_USED'
        assert provider_calls == []
        state = parse_qs(provider_url.query)['state'][0]
        staged = client.get(_META_CALLBACK, params={'state': state, 'code': 'INERT-mounted-code'})
        assert staged.status_code == 200, staged.text
        completion = _META_API + _META_ADMIN + '/complete'
        complete_body = {'flow_id': flow['flow_id']}
        for identity in (
            types.SimpleNamespace(id=actor, roles=['admin'], session_id=str(uuid4())),
            types.SimpleNamespace(id=str(uuid4()), roles=['admin'], session_id=session_id),
        ):
            principal['value'] = identity
            refused = client.post(completion, json=complete_body,
                                  headers={**command_headers, 'Idempotency-Key': str(uuid4())})
            assert refused.status_code == 409, refused.text
            assert refused.json()['detail']['code'] == 'OAUTH_STATE_INVALID'
        monkeypatch.delitem(client.app.dependency_overrides, supabase_auth.require_admin)
        assert client.post(completion, json=complete_body,
                           headers=command_headers).status_code in {401, 403}
        assert provider_calls == []
        principal['value'] = types.SimpleNamespace(id=actor, roles=['admin'], session_id=session_id)
        monkeypatch.setitem(client.app.dependency_overrides, supabase_auth.require_admin, admin)
        finished = client.post(completion, json=complete_body, headers=command_headers)
        assert finished.status_code == 200, finished.text
        assert provider_calls == [('INERT-mounted-code', _META_CALLBACK)]
        assert client.post(completion, json=complete_body,
                           headers=command_headers).json() == finished.json()
        assert len(provider_calls) == 1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(SocialOAuthFlow)) == 1
            assert db.scalar(select(func.count()).select_from(SocialAccount)) == 0
            assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
    finally:
        engine.dispose()
