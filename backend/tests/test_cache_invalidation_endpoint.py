"""The nightly must be able to clear the API's response caches (issue #231).

The seed writes the database, but the API went on serving its cached
responses until their TTLs expired. Production has no Redis
(``/health/detailed``: ``"redis_configured": false``), so every cache is in
the memory of each gunicorn worker, and a restart is the only other thing
that clears them. On 2026-09-07 ``/debt/national`` served the pre-seed
figure for hours after a successful seed.

These tests drive a real cached endpoint. They seed a row, read it so the
response is cached, change the database, and show that the stale answer
survives until the signed invalidation call, then disappears.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime

import pytest

SECRET = "test-only-invalidate-secret"
URL = "/api/v1/system/cache/invalidate"
FISCAL_YEARS = "/api/v1/audits/fiscal-years"


def _signed(body: dict, secret: str = SECRET):
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, {"content-type": "application/json", "x-revalidate-signature": sig}


def _add_period(db_session, country_id, pid, label, year):
    from models import FiscalPeriod

    db_session.add(
        FiscalPeriod(
            id=pid,
            country_id=country_id,
            label=label,
            start_date=datetime(year, 7, 1),
            end_date=datetime(year + 1, 6, 30),
        )
    )
    db_session.commit()


@pytest.fixture
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv("REVALIDATE_SECRET", SECRET)
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "cache-generation"))
    return tmp_path


def _warm_then_change(client, db_session, seed_country):
    """Cache a one-year answer, then add a second year to the database."""
    _add_period(db_session, seed_country.id, 9101, "FY 2023/24", 2023)
    first = client.get(FISCAL_YEARS).json()["data"]
    assert first == ["FY 2023/24"]

    _add_period(db_session, seed_country.id, 9102, "FY 2024/25", 2024)
    stale = client.get(FISCAL_YEARS).json()["data"]
    # Guard the guard: if this endpoint stops caching, the test can no longer
    # tell an invalidation from a cache that was never there.
    assert stale == ["FY 2023/24"], "endpoint is not cached; the test proves nothing"


def test_signed_invalidation_makes_new_data_visible(
    client, db_session, seed_country, configured
):
    _warm_then_change(client, db_session, seed_country)

    raw, headers = _signed({"ts": int(time.time()), "reason": "test"})
    res = client.post(URL, content=raw, headers=headers)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["invalidated"] is True
    assert body["local"]["cleared_entries"] >= 1

    fresh = client.get(FISCAL_YEARS).json()["data"]
    assert fresh == ["FY 2024/25", "FY 2023/24"]


def test_another_workers_invalidation_reaches_this_worker(
    client, db_session, seed_country, configured
):
    """Production runs gunicorn. The HTTP call lands on ONE worker, and every
    other worker holds its own in-process cache. They share the container's
    filesystem, so the endpoint bumps a generation marker there, and each
    worker clears its own caches the next time it serves a request after
    seeing the marker change. This test bumps the marker without touching
    this process's caches, which is what another worker's call looks like
    from here."""
    from cache import invalidation

    # This worker has served a request, so it has recorded a generation.
    _warm_then_change(client, db_session, seed_country)

    invalidation.bump_generation()  # another worker handled the call

    fresh = client.get(FISCAL_YEARS).json()["data"]
    assert fresh == ["FY 2024/25", "FY 2023/24"]


def test_unsigned_request_is_refused_and_clears_nothing(
    client, db_session, seed_country, configured
):
    _warm_then_change(client, db_session, seed_country)

    raw, headers = _signed({"ts": int(time.time())}, secret="wrong")
    assert client.post(URL, content=raw, headers=headers).status_code == 401
    assert client.post(URL, content=raw).status_code == 401

    assert client.get(FISCAL_YEARS).json()["data"] == ["FY 2023/24"]


def test_stale_signed_request_is_refused(client, configured):
    """A captured request must not become a way to empty the cache forever."""
    raw, headers = _signed({"ts": int(time.time()) - 3600})
    res = client.post(URL, content=raw, headers=headers)
    assert res.status_code == 401
    assert res.json()["detail"]["error"] == "stale_request"


def test_unconfigured_secret_is_503_not_open(client, monkeypatch, tmp_path):
    monkeypatch.delenv("REVALIDATE_SECRET", raising=False)
    monkeypatch.setenv("CACHE_GENERATION_FILE", str(tmp_path / "g"))
    raw, headers = _signed({"ts": int(time.time())})
    res = client.post(URL, content=raw, headers=headers)
    assert res.status_code == 503
    assert res.json()["detail"]["error"] == "invalidation_not_configured"


def test_unwritable_marker_fails_loudly(client, monkeypatch, tmp_path):
    """If the other workers cannot be told, the call must fail. Answering 200
    after clearing only one worker is the silent partial success this
    endpoint exists to remove."""
    monkeypatch.setenv("REVALIDATE_SECRET", SECRET)
    monkeypatch.setenv(
        "CACHE_GENERATION_FILE", str(tmp_path / "no-such-dir" / "g")
    )
    raw, headers = _signed({"ts": int(time.time())})
    res = client.post(URL, content=raw, headers=headers)
    assert res.status_code == 500
    assert res.json()["detail"]["error"] == "generation_marker_unwritable"


def test_redis_failure_fails_loudly(client, configured, monkeypatch):
    """With Redis configured, a failed delete must fail the call. The old
    ``RedisCache.clear_pattern`` logged the error and returned normally."""
    from cache.redis_cache import RedisCache

    class _Boom:
        def scan_iter(self, *a, **k):
            raise ConnectionError("redis down")

    probe = RedisCache.__new__(RedisCache)
    probe.client = _Boom()
    probe._memory_cache = {}
    probe.namespace = "t"
    RedisCache._instances.add(probe)
    try:
        raw, headers = _signed({"ts": int(time.time())})
        res = client.post(URL, content=raw, headers=headers)
    finally:
        RedisCache._instances.discard(probe)
    assert res.status_code == 500
    assert res.json()["detail"]["error"] == "redis_invalidation_failed"
