"""``GET /api/v1/pending-bills`` was never cached: its body held a datetime.

The database branch returned ``"last_updated": max(l.updated_at ...)`` — a
``datetime``. FastAPI encodes that on the way out, so the wire looked fine,
but ``RedisCache.set`` serialises with ``json.dumps`` and refused it on every
call::

    Cache set SKIPPED — the value for 'pending_bills:summary' can never be
    serialised (TypeError: Object of type datetime is not JSON serializable)

so every request re-ran the loans query and the entity join. The cache
deliberately does not coerce datetimes (see ``_json_default``): the handler
must hand it a JSON-native value, as ``vintage_iso`` and the other
``last_updated`` sites already do.

The in-memory fallback serialises too (since #184), so this reproduces
without Redis; the fake client below keeps redis-py's storage contract anyway
so the test exercises the production path.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import pytest
from models import DebtCategory, Entity, EntityType, Loan

URL = "/api/v1/pending-bills"
UPDATED_AT = datetime(2026, 9, 1, 8, 30, 15)


class FakeRedisClient:
    """redis-py's storage contract: only str/bytes/int/float may be stored."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):  # noqa: ARG002
        if not isinstance(value, (str, bytes, int, float)):
            raise TypeError(f"Invalid input of type: {type(value).__name__!r}")
        self.store[key] = value

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def keys(self, pattern):  # noqa: ARG002
        return []

    def flushdb(self):
        self.store.clear()


@pytest.fixture()
def endpoint_cache():
    """The instance ``main.cached`` writes to — NOT ``cache.redis_cache.cache``,
    which is a different RedisCache that this route never touches."""
    import main

    assert main.redis_cache is not None, "main.cached would bypass RedisCache"
    return main.redis_cache


@pytest.fixture()
def redis_client(endpoint_cache):
    from main import clear_all_caches

    fake = FakeRedisClient()
    original = endpoint_cache.client
    endpoint_cache.client = fake
    clear_all_caches()
    try:
        yield fake
    finally:
        endpoint_cache.client = original
        clear_all_caches()


@pytest.fixture()
def pending_bills(db_session, seed_country, seed_source_doc):
    entity = Entity(
        id=904,
        country_id=seed_country.id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    db_session.add(entity)
    db_session.add(
        Loan(
            entity_id=entity.id,
            lender="Pending Bills — National Government",
            debt_category=DebtCategory.PENDING_BILLS,
            principal=702.8e9,
            outstanding=702.8e9,
            issue_date=datetime(2025, 1, 1),
            currency="KES",
            source_document_id=seed_source_doc.id,
            provenance={"fiscal_year": "FY 2024/25"},
            created_at=UPDATED_AT,
            updated_at=UPDATED_AT,
        )
    )
    db_session.commit()
    return db_session


def test_the_harness_can_observe_a_successful_write(endpoint_cache, redis_client):
    """POSITIVE CONTROL — an inert fake would make "nothing cached" meaningless."""
    endpoint_cache.set("probe:dict", {"a": 1}, ttl=60)
    assert redis_client.store
    assert endpoint_cache.get("probe:dict") == {"a": 1}


def test_the_database_body_is_json_native(pending_bills):
    """The handler's own return value, before FastAPI's encoder can mask it."""
    import asyncio

    from main import get_pending_bills

    body = asyncio.run(get_pending_bills.__wrapped__(db=pending_bills))
    assert body["data_source"] == "database", body
    json.dumps(body)  # raises TypeError on the pre-fix datetime
    assert body["last_updated"] == UPDATED_AT.isoformat()


def test_the_response_reaches_the_cache(
    client, endpoint_cache, redis_client, pending_bills, caplog
):
    skipped_before = endpoint_cache._unserialisable_values
    with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
        resp = client.get(URL)
    assert resp.status_code == 200, resp.text
    assert resp.json()["data_source"] == "database"

    assert not [r for r in caplog.records if "SKIPPED" in r.getMessage()], (
        "the cache refused the body as unserialisable"
    )
    assert endpoint_cache._unserialisable_values == skipped_before
    assert any("pending_bills:summary" in k for k in redis_client.store), (
        f"nothing written under pending_bills:summary: {list(redis_client.store)}"
    )


def test_a_second_request_is_served_from_the_cache(
    client, db_session, redis_client, pending_bills
):
    """Delete the rows between requests: only a cache hit can still answer."""
    first = client.get(URL)
    assert first.status_code == 200, first.text
    assert first.json()["data_source"] == "database"

    db_session.query(Loan).filter(
        Loan.debt_category == DebtCategory.PENDING_BILLS
    ).delete()
    db_session.commit()

    second = client.get(URL)
    assert second.status_code == 200, second.text
    assert second.json()["data_source"] == "database", (
        "the second request re-ran the query against an emptied table, so the "
        f"first was never cached (got data_source={second.json()['data_source']!r})"
    )
    assert second.content == first.content, (
        "the cached body differs from the uncached one; the fix must not "
        "change what the endpoint says"
    )


def test_last_updated_wire_format_is_unchanged(client, redis_client, pending_bills):
    """FastAPI encoded the datetime with ``isoformat()``; the string must match,
    so the frontend (``last_updated?: string``) sees the same value as before."""
    body = client.get(URL).json()
    assert body["last_updated"] == "2026-09-01T08:30:15"
