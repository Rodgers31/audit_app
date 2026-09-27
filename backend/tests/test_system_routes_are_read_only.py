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

from fastapi.routing import APIRoute

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


def test_system_namespace_registers_only_reads():
    system_routes = [
        r
        for r in app.routes
        if isinstance(r, APIRoute) and r.path.startswith(SYSTEM_PREFIX)
    ]
    # Not vacuous: the status routes the frontend reads must still be here.
    assert {r.path for r in system_routes} >= {
        "/api/v1/system/seeder-status",
        "/api/v1/system/pipeline-health",
    }

    writers = sorted(
        f"{sorted(r.methods - READ_METHODS)} {r.path}"
        for r in system_routes
        if r.methods - READ_METHODS
    )
    assert writers == [], f"write routes under {SYSTEM_PREFIX}: {writers}"
