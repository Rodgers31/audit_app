"""Whole-cohort latency accounting over real owned PostgreSQL transactions.

The 150 ms driver cost is a deterministic budget simulation, not a measured
network RTT. Separate release receipts contain actual sleeping-driver runs.
"""
from collections import Counter
from types import SimpleNamespace
import json
import time

import pytest
from sqlalchemy import event, select, func

from models import IngestionJob
from social.generation import integration
from social.generation.models import SourceCursor
from social.models import SocialPost, SocialPostRevision
from native_worker_fixture import restricted
from test_b83_generation_postgres import pg, no_publication
from test_automatic_cohort_timeout_postgres import ingest_cohort, automatic, enabled


@pytest.mark.parametrize('mode', ['fresh', 'partial_recovery', 'retained_replay', 'all_changed'])
def test_full_financial_cohort_fits_conservative_driver_budget(restricted, tmp_path, monkeypatch, mode):
    factory, engine, _, _ = restricted
    enabled(factory, monkeypatch)
    monkeypatch.setenv('SOCIAL_REPORT_GENERATION_ENABLED', 'false')
    first = ingest_cohort(factory, tmp_path)
    if mode == 'partial_recovery':
        from seeding.source_observations import read_native_financial_record_ids
        ids = read_native_financial_record_ids(factory, ingestion_id=first, domain='pending_bills')
        partial = integration.maybe_generate_committed(factory, record_ids=ids[:3],
            ingestion_id=first, domain='pending_bills')
        assert partial['baselines'] == 3 and partial['drafts_created'] == 0
    elif mode in ('retained_replay', 'all_changed'):
        assert automatic(factory, first)['baselines'] == 46
    job = (first if mode == 'fresh' else ingest_cohort(factory, tmp_path,
        retained=True, correction='all' if mode == 'all_changed' else None))

    calls = Counter()
    cost = [0.0]
    original_clock = time.monotonic
    clock = SimpleNamespace(monotonic=lambda: original_clock() + cost[0])
    def driver_cost(_conn, _cursor, statement, _parameters, _context, _many):
        calls[statement.split()[0].upper()] += 1
        cost[0] += .150
    monkeypatch.setattr(integration, 'time', clock)
    event.listen(engine, 'after_cursor_execute', driver_cost)
    started = clock.monotonic()
    try:
        outcome = automatic(factory, job)
    finally:
        elapsed = clock.monotonic() - started
        event.remove(engine, 'after_cursor_execute', driver_cost)
    print('NETWORK_BUDGET_PROFILE ' + json.dumps(dict(mode=mode,
        simulated_driver_seconds=.150, driver_calls=sum(calls.values()),
        elapsed_accounted_seconds=elapsed, result=outcome), sort_keys=True))
    assert outcome['state'] == 'completed' and outcome['processed'] == 46, outcome
    assert outcome['refused'] == 0
    assert outcome['drafts_created'] == (46 if mode == 'all_changed' else 0)
    assert outcome['baselines'] == {'fresh':46, 'partial_recovery':43,
        'retained_replay':0, 'all_changed':0}[mode]
    assert outcome['unchanged'] == {'fresh':0, 'partial_recovery':3,
        'retained_replay':46, 'all_changed':0}[mode]
    # A bounded call-count contract prevents replacing the query reductions
    # with only a larger clock allowance. Include outcome persistence calls.
    assert sum(calls.values()) <= (3100 if mode == 'all_changed' else 1500)
    with factory() as db:
        root = db.scalar(select(SourceCursor).where(
            SourceCursor.source_key == 'cob:financial:pending_bills:baseline'))
        assert root.evidence_version == job and root.report_state['financial_baseline'] == 2
        assert root.report_state['completed_count'] == 46
        assert len(root.report_state['completion']['records']) == 46
        posts = list(db.scalars(select(SocialPost)))
        assert len(posts) == (46 if mode == 'all_changed' else 0)
        assert all(p.editorial_state == 'pending_review' for p in posts)
        if mode == 'all_changed':
            revisions = list(db.scalars(select(SocialPostRevision)))
            assert len(revisions) == 46
            assert all(r.evidence_snapshot['worker_authority']['kind'] == 'financial' for r in revisions)
        assert db.get(IngestionJob, job).status.name == 'COMPLETED'
    no_publication(factory)
