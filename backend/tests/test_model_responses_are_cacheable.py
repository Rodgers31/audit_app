"""Endpoints that return a Pydantic model were never cached under Redis.

Issue #184. ``RedisCache.set`` serialised with a bare ``json.dumps(value)``.
An endpoint declaring ``response_model`` returns the **model**, and
``json.dumps(BaseModel)`` raises ``TypeError``. One ``except Exception``
wrapped the whole method, so the write was dropped, the entry never appeared,
and every request re-ran the query. The only trace was

    Cache set error: Object of type AuditSummaryResponse is not JSON serializable

which reads like a Redis hiccup and is indistinguishable from one.

WHY IT SURVIVED, and why a careless test here proves nothing. Redis is not
configured in development or in CI, so ``self.client`` is ``None`` and the
in-memory branch stored the object **unserialised**. The defect is invisible
on the path every test takes. A test that does not drive a client which
actually serialises will pass against the broken code.

So these tests install a client with redis-py's storage contract — only
``str``/``bytes``/``int``/``float`` may be stored — and
``test_the_harness_can_observe_a_successful_write`` proves that harness can
record a write, so "nothing was cached" cannot be confused with "the fake is
inert".

The fix normalises in ``RedisCache.set`` for BOTH branches, so the in-memory
cache now stores what Redis would store. Development and CI no longer differ
from production on the one axis that hid this.
"""

from __future__ import annotations

import datetime
import logging
import re

import pytest

from models import PopulationData

POPULATION_URL = "/api/v1/economic/population/latest"


class FakeRedisClient:
    """Storage contract of a real redis-py client.

    ``setex`` refuses anything that is not ``str``/``bytes``/``int``/``float``
    — the same refusal a real server makes — so a "fix" that hands the model
    straight to the client instead of serialising it still fails here.
    """

    def __init__(self):
        self.store: dict[str, str] = {}

    def get(self, key):
        return self.store.get(key)

    def setex(self, key, ttl, value):
        if not isinstance(value, (str, bytes, int, float)):
            raise TypeError(
                f"Invalid input of type: {type(value).__name__!r}. "
                "Convert to a bytes, string, int or float first."
            )
        self.store[key] = value

    def delete(self, *keys):
        for k in keys:
            self.store.pop(k, None)

    def keys(self, pattern):  # noqa: ARG002
        return []

    def flushdb(self):
        self.store.clear()

    def ping(self):
        return True

    def info(self):
        return {"connected_clients": 1, "used_memory_human": "1M", "uptime_in_seconds": 1}


@pytest.fixture()
def redis_client():
    """Point the module-level cache at a serialising client, as production is."""
    import cache.redis_cache as rc

    fake = FakeRedisClient()
    original = rc.cache.client
    rc.cache.client = fake
    rc.cache._memory_cache.clear()
    try:
        yield fake
    finally:
        rc.cache.client = original
        rc.cache._memory_cache.clear()


@pytest.fixture()
def seeded_population(db_session):
    db_session.add(
        PopulationData(entity_id=None, year=2019, total_population=47_564_296)
    )
    db_session.commit()


@pytest.fixture()
def seeded_audits(db_session, seed_entity, seed_fiscal_period, seed_source_doc):
    """Enough audit findings that wiping them visibly changes every response."""
    from models import Audit, Severity

    for year, amount in ((2022, 1_000_000.0), (2023, 2_500_000.0)):
        db_session.add(
            Audit(
                entity_id=seed_entity.id,
                period_id=seed_fiscal_period.id,
                source_document_id=seed_source_doc.id,
                finding_text=f"probe finding {year}",
                severity=Severity.CRITICAL,
                query_type="Irregular Expenditure",
                amount=amount,
                audit_year=year,
                publishable=True,
            )
        )
    db_session.commit()


#: Every cached endpoint that returns a Pydantic model rather than a dict.
#: Established by driving the live route table against a serialising client,
#: not by reading the source — see the module docstring.
MODEL_ROUTES = [
    "/api/v1/audit/summary",
    "/api/v1/audit/trends",
    "/api/v1/economic/summary",
    "/api/v1/economic/population/latest",
]


class TestModelReturningEndpointsAreCached:
    def test_the_harness_can_observe_a_successful_write(self, redis_client):
        """POSITIVE CONTROL — without this, "nothing cached" proves nothing.

        If the fake client could never record a write, every assertion below
        would pass for the wrong reason.
        """
        import cache.redis_cache as rc

        rc.cache.set("probe:dict", {"a": 1}, ttl=60)
        assert redis_client.store, (
            "the fake client recorded nothing for a plain dict — the harness "
            "is inert and the tests below would be false negatives"
        )
        assert rc.cache.get("probe:dict") == {"a": 1}

    def test_the_response_reaches_the_cache(
        self, client, redis_client, seeded_population
    ):
        """RED before the fix: the store is empty and the log says only
        "Cache set error", the same thing it says when Redis is down."""
        resp = client.get(POPULATION_URL)
        assert resp.status_code == 200, resp.text

        assert redis_client.store, (
            "the response never reached Redis. Every request re-runs the "
            "query; the endpoint is uncached in production."
        )

    def test_a_second_request_is_served_from_the_cache(
        self, client, db_session, redis_client, seeded_population
    ):
        """The behaviour the cache exists for, proved without reading internals.

        The row is deleted between the two requests. A handler that re-runs
        answers 404; only a cache hit can still answer 200.
        """
        first = client.get(POPULATION_URL)
        assert first.status_code == 200, first.text

        db_session.query(PopulationData).delete()
        db_session.commit()

        second = client.get(POPULATION_URL)
        assert second.status_code == 200, (
            "the second request re-ran the query against a now-empty table, "
            f"so it was never cached (got {second.status_code})"
        )
        assert second.content == first.content, (
            "the cached response differs from the uncached one byte-for-byte. "
            "A performance fix must not change what the endpoint says."
        )


class TestSerialisationFailureIsReportable:
    """"Redis is down" and "this value can never be cached" must not look alike.

    The first is transient and self-healing. The second is permanent and needs
    a code change. Reporting both as ``Cache set error`` is why this ran
    uncached in production long enough to be found in a PR review rather than
    by an alert.
    """

    def _cache_with(self, client):
        from cache.redis_cache import RedisCache

        c = RedisCache.__new__(RedisCache)
        c.redis_url = "redis://test"
        c.client = client
        c._memory_cache = {}
        c._memory_cache_max_size = 8
        RedisCache._instances.add(c)
        return c

    def test_an_unserialisable_value_is_counted_as_such(self, caplog):
        class _Unserialisable:
            pass

        cache = self._cache_with(FakeRedisClient())
        with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
            cache.set("k", _Unserialisable(), ttl=60)

        health = cache.health_check()
        assert health["status"] == "healthy", (
            "this must be asserted against a WORKING Redis — a healthy "
            "connection being handed uncacheable values is the production "
            f"state issue #184 sat in. Got {health!r}"
        )
        assert health.get("unserialisable_values") == 1, (
            "a value that can never be cached left no structural trace — an "
            "operator has only a log line that looks like a Redis blip. "
            f"health_check() returned {health!r}"
        )

    def test_a_redis_outage_is_not_counted_as_a_serialisation_failure(self, caplog):
        class _Down(FakeRedisClient):
            def setex(self, key, ttl, value):
                raise ConnectionError("Error 61 connecting to localhost:6379")

            def ping(self):
                raise ConnectionError("Error 61 connecting to localhost:6379")

        cache = self._cache_with(_Down())
        with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
            cache.set("k", {"a": 1}, ttl=60)

        health = cache.health_check()
        assert health.get("unserialisable_values") == 0, (
            "a transport outage was classified as a permanent serialisation "
            "failure; the two must stay distinguishable"
        )


# ── The route sweep ───────────────────────────────────────────────────────
#
# Issue #266 is why this is more than "call every route once". The sweep used
# to seed only ``PopulationData``, so most routes answered from their
# empty/no_data branch — and a 200 was counted as "exercised". GET
# /api/v1/pending-bills put a datetime into ``last_updated`` ONLY on its
# database branch, the sweep never reached that branch, and the endpoint ran
# uncached with this guard green.
#
# So the sweep now seeds representative rows, sweeps, wipes every table and
# sweeps again. A route whose seeded answer is the same as its empty-database
# answer never reached a branch that reads rows, whatever its status code, and
# is reported. The set of such routes must equal ``_EMPTY_BRANCH_ALLOWLIST``
# exactly — an unexplained empty route fails, and so does an allowlist entry
# that has since become reachable.

#: What each ``{param}`` in a cached route's path is filled with. A new path
#: parameter name fails the sweep until someone decides what it should be.
#: ``047`` is COUNTY_MAPPING's code for Mombasa, the county
#: ``representative_rows`` seeds under its production name.
_SWEEP_PATH_PARAMS = {"county_id": "047", "country_id": "1"}

#: Query strings a route needs to get past validation to its handler body.
_SWEEP_QUERY = {
    "/api/v1/audit/money-flow/national": "year=FY2024/25",
    "/api/v1/money-flow/all-counties": "year=FY2024/25",
}

#: Cached routes that answer from an empty branch EVEN WITH representative
#: rows seeded, and why no seed can change that. Every entry is a route this
#: guard cannot vouch for, so each needs a reason a reviewer can check.
_EMPTY_BRANCH_ALLOWLIST = {}

#: Which branch each pending-bills route must have answered from, per
#: scenario. Those two routes used to read a ``pending_bills`` table first and
#: fall back to ``Loan(debt_category=PENDING_BILLS)``; nothing ever wrote the
#: table and #137 P6 removed it, so the loan rows the publication gate admits
#: are the only branch left. The sweep still checks it reached that branch.
_SCENARIOS = {
    "pending_bills_from_loans": {
        "/api/v1/pending-bills/summary": "loans_table_fallback",
        "/api/v1/pending-bills/counties/{county_id}": "loans_table_fallback",
    },
}

_NO_DATA_MARKERS = (
    ("status", "no_data"),
    ("data_source", "none"),
    ("data_source", "database_empty"),
)

#: ``generated_at`` and friends differ between any two requests; they are not
#: evidence that a route read a row.
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?"
)


@pytest.fixture()
def representative_rows(db_session, seed_entity, seed_fiscal_period, seed_source_doc):
    """One row, or a few, behind every branch a cached route builds from rows.

    The county is named "<Name> County" because several county handlers match
    ``canonical_name == f"{name} County"`` and nothing else (the conftest
    "Nairobi" entity reaches none of them). Fact rows carry a page locator,
    a document with a URL and ``publishable``, because the publication gates
    drop anything less before the handler's populated branch is reached.
    """
    from models import (
        Audit,
        BudgetLine,
        DebtCategory,
        DebtTimeline,
        EconomicIndicator,
        Entity,
        Extraction,
        EntityType,
        FigureBasis,
        FiscalSummary,
        GDPData,
        Loan,
        PopulationData,
        RevenueBySource,
        Severity,
    )

    country_id = seed_entity.country_id
    period_id = seed_fiscal_period.id
    doc_id = seed_source_doc.id
    # Freshness needs an accepted fact AND the source's publication date.
    # Without this the sweep only sees its unknown-data branch.
    seed_source_doc.meta = {"publication_date": "2024-08-01"}
    db_session.flush()
    fact = dict(source_document_id=doc_id, publishable=True, page_ref="p. 12")

    national = Entity(
        country_id=country_id,
        type=EntityType.NATIONAL,
        canonical_name="National Government",
        slug="national-government",
    )
    county = Entity(
        country_id=country_id,
        type=EntityType.COUNTY,
        canonical_name="Mombasa County",
        slug="mombasa-county",
        meta={
            "county_code": _SWEEP_PATH_PARAMS["county_id"],
            "missing_funds_cases": [
                {
                    "case_id": "MF-1",
                    "source_document_id": doc_id,
                    "page_ref": "p. 12",
                    "amount": "KES 1.5B",
                    "status": "Under investigation",
                    "period": "FY2024/25",
                    "description": "probe case",
                }
            ],
        },
    )
    ministry = Entity(
        country_id=country_id,
        type=EntityType.MINISTRY,
        canonical_name="Ministry of Health",
        slug="ministry-of-health",
    )
    db_session.add_all([national, county, ministry])
    db_session.flush()

    db_session.add_all(
        [
            PopulationData(entity_id=None, year=2019, total_population=47_564_296),
            GDPData(
                entity_id=None,
                year=2024,
                gdp_value=16_000_000_000_000,
                source_document_id=doc_id,
            ),
            EconomicIndicator(
                indicator_type="total_national_gdp",
                indicator_date=datetime.datetime(2024, 12, 31),
                value=16_000_000,
            ),
            EconomicIndicator(
                indicator_type="inflation_rate",
                indicator_date=datetime.datetime(2025, 6, 30),
                value=4.1,
            ),
            # ── debt ──
            Loan(
                entity_id=national.id,
                lender="World Bank IDA",
                debt_category=DebtCategory.EXTERNAL_MULTILATERAL,
                principal=1.2e12,
                outstanding=9.6e11,
                interest_rate=1.25,
                issue_date=datetime.datetime(2020, 1, 1),
                maturity_date=datetime.datetime(2045, 1, 1),
                currency="KES",
                basis=FigureBasis.ACTUAL,
                **fact,
            ),
            Loan(
                entity_id=national.id,
                lender="Treasury Bond FXD1/2024/10",
                debt_category=DebtCategory.DOMESTIC_BONDS,
                principal=6.0e12,
                outstanding=4.8e12,
                interest_rate=16.0,
                issue_date=datetime.datetime(2024, 1, 1),
                maturity_date=datetime.datetime(2034, 1, 1),
                currency="KES",
                basis=FigureBasis.ACTUAL,
                **fact,
            ),
            DebtTimeline(
                year=2023,
                external=5.0e12,
                domestic=5.1e12,
                total=10.1e12,
                gdp=14.8e12,
                gdp_ratio=68.2,
                unit="KES",
                source_document_id=doc_id,
            ),
            DebtTimeline(
                year=2024,
                external=5.2e12,
                domestic=5.8e12,
                total=11.0e12,
                gdp=16.0e12,
                gdp_ratio=68.8,
                unit="KES",
                source_document_id=doc_id,
            ),
            FiscalSummary(
                fiscal_year="2024/25",
                appropriated_budget=4.0e12,
                total_revenue=3.0e12,
                tax_revenue=2.6e12,
                non_tax_revenue=0.4e12,
                total_borrowing=0.9e12,
                debt_service_cost=1.2e12,
                development_spending=0.7e12,
                recurrent_spending=2.5e12,
                county_allocation=0.4e12,
                **fact,
            ),
            RevenueBySource(
                fiscal_year="FY2024/25",
                revenue_type="VAT",
                category="tax",
                amount_billion_kes=800,
                meta={"basis": "published"},
                **fact,
            ),
            # ── pending bills: both branches' source rows ──
            # The two Loan rows are what GET /pending-bills reads — the branch
            # #266 hid in. A county one exercises the county/national split.
            Loan(
                entity_id=national.id,
                lender="MDA pending bills",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=5e11,
                outstanding=5e11,
                issue_date=datetime.datetime(2025, 6, 30),
                currency="KES",
                # Declared as the fetcher stamps a BROP national line; the
                # publication gate withholds any pending-bills row that does
                # not declare its publication (#265).
                # Stated at the SAME day as the county row below, as the 2026
                # BROP and the CoB year-end report both are: only then does
                # /pending-bills/summary build its one-date total and trend,
                # which are branches the sweep must reach (review of #282).
                provenance={
                    "fiscal_year": "FY 2025/26",
                    "source": "cob_pending_bills_etl",
                    "publication": "treasury_brop",
                    "category": "mda",
                    "as_at": "2026-06-30",
                },
                **fact,
            ),
            Loan(
                entity_id=county.id,
                lender="Mombasa County pending bills",
                debt_category=DebtCategory.PENDING_BILLS,
                principal=1e11,
                outstanding=1e11,
                issue_date=datetime.datetime(2026, 6, 30),
                currency="KES",
                # Declared as the fetcher stamps a CoB year-end county row
                # (#238): a single dict with the side, the publication and the
                # day the figure is a stock on.
                provenance={
                    "fiscal_year": "FY 2025/26",
                    "source": "cob_pending_bills_etl",
                    "publication": "cob_cbirr_year_end",
                    "category": "county",
                    "as_at": "2026-06-30",
                },
                **fact,
            ),
            # ── budgets: county sector lines, and a national line with a
            # commitment (execution_by_sector reads only those) ──
            BudgetLine(
                entity_id=county.id,
                period_id=period_id,
                category="Health",
                allocated_amount=1e10,
                actual_spent=6e9,
                currency="KES",
                line_type="component",
                basis=FigureBasis.ACTUAL,
                **fact,
            ),
            BudgetLine(
                entity_id=county.id,
                period_id=period_id,
                category="Education",
                allocated_amount=2e10,
                actual_spent=1.5e10,
                currency="KES",
                line_type="component",
                basis=FigureBasis.ACTUAL,
                **fact,
            ),
            BudgetLine(
                entity_id=national.id,
                period_id=period_id,
                category="Health",
                allocated_amount=2e11,
                actual_spent=1e11,
                committed_amount=1.5e11,
                currency="KES",
                line_type="component",
                basis=FigureBasis.ACTUAL,
                **fact,
            ),
            # ── audits: county findings across two years, and a ministry
            # finding for the federal report ──
            Audit(
                entity_id=county.id,
                period_id=period_id,
                finding_text="Irregular expenditure of KES 1,000,000",
                severity=Severity.CRITICAL,
                query_type="Irregular Expenditure",
                amount=1_000_000,
                audit_year=2022,
                audit_opinion="Qualified Opinion",
                **fact,
            ),
            Audit(
                entity_id=county.id,
                period_id=period_id,
                finding_text="Irregular expenditure of KES 2,500,000",
                severity=Severity.CRITICAL,
                query_type="Irregular Expenditure",
                amount=2_500_000,
                audit_year=2023,
                audit_opinion="Qualified Opinion",
                **fact,
            ),
            Audit(
                entity_id=ministry.id,
                period_id=period_id,
                finding_text="Unsupported payments of KES 1,000,000",
                severity=Severity.CRITICAL,
                query_type="Unsupported Expenditure",
                amount=1_000_000,
                audit_year=2024,
                **fact,
            ),
        ]
    )
    # ── an extracted "Unaccounted …" finding. Since the audit-headline work
    # (#233), /accountability/missing-funds lists the findings the
    # Auditor-General titled "Unaccounted …"/"Loss of Funds", read through their
    # extraction rows, instead of Entity.meta cases. The older path ignores this
    # row, so the sweep reaches the populated branch either way.
    unaccounted = Extraction(
        source_document_id=doc_id,
        extractor="oag_blue_book",
        page_number=12,
        extracted_json={
            "title": "Unaccounted for Imprests",
            "heading": "Basis for Qualified Opinion",
            "pdf_page": 12,
            "paragraph_no": 7,
            "finding_text": (
                "Unaccounted for Imprests. Imprests of KES 3,000,000 issued "
                "during the year had not been surrendered or accounted for "
                "at the time of audit."
            ),
        },
    )
    db_session.add(unaccounted)
    db_session.flush()
    db_session.add(
        Audit(
            entity_id=ministry.id,
            period_id=period_id,
            extraction_id=unaccounted.id,
            finding_text=(
                "Unaccounted for Imprests. Imprests of KES 3,000,000 issued "
                "during the year had not been surrendered or accounted for "
                "at the time of audit."
            ),
            severity=Severity.CRITICAL,
            query_type="Basis for Qualified Opinion",
            amount=3_000_000,
            audit_year=2024,
            **fact,
        )
    )
    db_session.commit()


def _wipe(db_session):
    from models import Base

    for table in reversed(Base.metadata.sorted_tables):
        db_session.execute(table.delete())
    db_session.commit()


def _cached_get_routes(app):
    return [
        r
        for r in TestNoCachedRouteSilentlyFailsToSerialise._walk(app.routes)
        if "GET" in (getattr(r, "methods", None) or set())
        and TestNoCachedRouteSilentlyFailsToSerialise._is_cached(
            getattr(r, "endpoint", None)
        )
    ]


def _url_for(path):
    def fill(m):
        name = m.group(1)
        assert name in _SWEEP_PATH_PARAMS, (
            f"{path} has a path parameter {{{name}}} the sweep has no value for. "
            "Add one to _SWEEP_PATH_PARAMS that resolves to a seeded row."
        )
        return _SWEEP_PATH_PARAMS[name]

    url = re.sub(r"\{(\w+)(:[^}]+)?\}", fill, path)
    return f"{url}?{_SWEEP_QUERY[path]}" if path in _SWEEP_QUERY else url


def _sweep(client, redis_client, caplog, routes):
    """Request every route once with every cache empty.

    Returns ``{path: (status, body, normalised_text, refusals)}``. A refusal
    is read from the cache's own ``unserialisable_values`` counter, on every
    RedisCache instance (routers/money_flow.py keeps a private one), and from
    its log line, so neither channel going quiet can hide one.
    """
    import main
    from cache.redis_cache import RedisCache

    answers = {}
    for route in sorted(routes, key=lambda r: r.path):
        main.clear_all_caches()
        redis_client.store.clear()
        caplog.clear()
        before = {id(c): c._unserialisable_values for c in RedisCache._instances}
        with caplog.at_level(logging.ERROR, logger="cache.redis_cache"):
            resp = client.get(_url_for(route.path))
        refusals = [
            c._last_unserialisable
            for c in RedisCache._instances
            if c._unserialisable_values > before.get(id(c), 0)
        ] or [
            r.getMessage()
            for r in caplog.records
            if "serialis" in r.getMessage().lower()
            or "not JSON serializable" in r.getMessage()
        ]
        try:
            body = resp.json()
        except ValueError:
            body = None
        answers[route.path] = (
            resp.status_code,
            body,
            _TIMESTAMP.sub("<ts>", resp.text),
            refusals,
        )
    return answers


def _empty_branch_reason(seeded, empty):
    """Why a seeded answer is not evidence of a populated branch, or None."""
    status, body, text, _ = seeded
    if status != 200:
        return f"HTTP {status}"
    if isinstance(body, dict):
        for key, value in _NO_DATA_MARKERS:
            if body.get(key) == value:
                return f'{key}="{value}"'
    if (status, text) == (empty[0], empty[2]):
        return "same body as on an empty database: the seed never reached it"
    return None


def _report(seeded, empty_reasons):
    width = max(len(p) for p in seeded)
    lines = []
    for path in sorted(seeded):
        if path in empty_reasons:
            verdict = f"EMPTY  {empty_reasons[path]}"
            if path in _EMPTY_BRANCH_ALLOWLIST:
                verdict += "  [allowlisted]"
        else:
            verdict = "populated"
        lines.append(f"  {path:<{width}}  {verdict}")
    return "\n".join(lines)


class TestNoCachedRouteSilentlyFailsToSerialise:
    """The durable guard: this catches the NEXT model-returning endpoint.

    Walking the live route table rather than a hand-kept list means an
    endpoint added later is covered without anyone remembering to add it.
    """

    @staticmethod
    def _walk(routes):
        for r in routes:
            included = getattr(r, "original_router", None)
            if included is not None:
                yield from TestNoCachedRouteSilentlyFailsToSerialise._walk(
                    included.routes
                )
            elif getattr(r, "path", None) is not None:
                yield r

    @staticmethod
    def _is_cached(fn):
        """``functools.wraps`` overwrites ``__qualname__``; the code object's
        ``co_qualname`` still names where the function was defined."""
        seen = set()
        while fn is not None and id(fn) not in seen:
            seen.add(id(fn))
            code = getattr(fn, "__code__", None)
            if code is not None and "cached.<locals>" in getattr(
                code, "co_qualname", ""
            ):
                return True
            fn = getattr(fn, "__wrapped__", None)
        return False

    @pytest.mark.parametrize("scenario", sorted(_SCENARIOS))
    def test_no_cached_endpoint_fails_to_serialise(
        self,
        client,
        db_session,
        redis_client,
        representative_rows,
        caplog,
        monkeypatch,
        scenario,
    ):
        import main

        monkeypatch.setattr(main.redis_cache, "client", redis_client)

        routes = _cached_get_routes(main.app)
        assert len(routes) >= 30, (
            f"only {len(routes)} cached routes found — the route walk broke "
            "and this guard is inspecting almost nothing"
        )
        live = {r.path for r in routes}
        stale_config = (set(_SWEEP_QUERY) | set(_EMPTY_BRANCH_ALLOWLIST)) - live
        assert not stale_config, (
            f"sweep configuration names routes that are not cached GET routes: "
            f"{sorted(stale_config)}"
        )

        seeded = _sweep(client, redis_client, caplog, routes)
        _wipe(db_session)
        empty = _sweep(client, redis_client, caplog, routes)

        refusals = [
            (f"{p} ({state})", m)
            for state, answers in (("seeded", seeded), ("empty", empty))
            for p, (*_, found) in answers.items()
            for m in found
        ]
        assert (
            not refusals
        ), "cached endpoints whose value cannot be stored:\n" + "\n".join(
            f"  {p}\n     {m}" for p, m in refusals
        )

        empty_reasons = {
            p: reason
            for p in seeded
            if (reason := _empty_branch_reason(seeded[p], empty[p])) is not None
        }
        report = _report(seeded, empty_reasons)
        print(f"\ncached-route sweep, scenario {scenario}:\n{report}")

        unexplained = set(empty_reasons) - set(_EMPTY_BRANCH_ALLOWLIST)
        assert not unexplained, (
            f"{len(unexplained)} cached route(s) answered from an empty branch "
            "with representative rows seeded, so this sweep never tested the "
            "branch that serialises real data — the gap issue #266 fell "
            "through. Seed what they read in representative_rows, or allowlist "
            "them with a reason.\n" + report
        )
        reachable_now = set(_EMPTY_BRANCH_ALLOWLIST) - set(empty_reasons)
        assert not reachable_now, (
            f"allowlisted route(s) now reach a populated branch: "
            f"{sorted(reachable_now)}. Remove them from _EMPTY_BRANCH_ALLOWLIST "
            "so the guard covers them.\n" + report
        )

        for path, expected in _SCENARIOS[scenario].items():
            got = seeded[path][1].get("data_source")
            assert got == expected, (
                f"scenario {scenario!r} was meant to drive {path} through its "
                f"{expected!r} branch, but it answered from {got!r}"
            )

    def test_the_sweep_sees_a_refusal_on_a_populated_branch_only(
        self, client, db_session, redis_client, representative_rows, caplog, monkeypatch
    ):
        """POSITIVE CONTROL — the shape of #266, on a route mounted for this test.

        It returns a datetime only when a PENDING_BILLS loan exists. The sweep
        must report the refusal when rows are seeded, and must classify the
        same route as empty-branch once they are gone. A sweep that could not
        do both would be green on #266 for the reason it used to be.
        """
        import main
        from database import get_db
        from fastapi import Depends
        from models import DebtCategory, Loan

        monkeypatch.setattr(main.redis_cache, "client", redis_client)
        path = "/api/v1/__sweep_positive_control__"

        @main.cached(key_prefix="sweep_positive_control", ttl=60)
        async def probe(db=Depends(get_db)):
            rows = (
                db.query(Loan)
                .filter(Loan.debt_category == DebtCategory.PENDING_BILLS)
                .all()
            )
            if not rows:
                return {"status": "no_data", "last_updated": None}
            return {
                "status": "success",
                "last_updated": max(r.updated_at for r in rows),
            }

        main.app.add_api_route(path, probe, methods=["GET"])
        try:
            routes = [r for r in _cached_get_routes(main.app) if r.path == path]
            assert len(routes) == 1, "the route walk did not find the mounted probe"

            seeded = _sweep(client, redis_client, caplog, routes)
            _wipe(db_session)
            empty = _sweep(client, redis_client, caplog, routes)
        finally:
            main.app.router.routes[:] = [
                r for r in main.app.router.routes if getattr(r, "path", None) != path
            ]

        assert seeded[path][0] == 200
        assert (
            _empty_branch_reason(seeded[path], empty[path]) is None
        ), "the seeded answer should count as populated"
        assert any(
            "datetime" in m for m in seeded[path][3]
        ), f"the sweep did not see the datetime refusal: {seeded[path][3]!r}"
        assert empty[path][3] == [], "the empty branch is serialisable"
        assert _empty_branch_reason(empty[path], empty[path]) == 'status="no_data"'


class TestCachedAndUncachedBodiesAreIdentical:
    """A performance fix must not change one byte of what the API says.

    The cached path returns a dict, which FastAPI re-validates against
    ``response_model``; the uncached path returns the model itself. Those are
    two different code paths through serialisation, and if they disagreed the
    cache would be quietly rewriting published figures — a behaviour change
    hiding inside a performance fix.

    The rows every one of these endpoints reads are deleted between the two
    requests, so a handler that re-ran could not produce the first body again.
    That, and not an internal counter, is what makes the second response
    provably the cached one.
    """

    @pytest.mark.parametrize("url", MODEL_ROUTES)
    def test_the_cached_body_is_byte_identical(
        self, client, db_session, redis_client, seeded_population, seeded_audits, url
    ):
        from models import Audit

        assert not redis_client.store
        first = client.get(url)
        assert first.status_code == 200, first.text
        assert redis_client.store, f"{url} never reached the cache"

        db_session.query(Audit).delete()
        db_session.query(PopulationData).delete()
        db_session.commit()

        second = client.get(url)
        assert second.status_code == first.status_code
        assert second.content == first.content, (
            f"{url} answers differently from cache than from the database.\n"
            f"  uncached: {first.content[:400]!r}\n"
            f"  cached:   {second.content[:400]!r}"
        )
