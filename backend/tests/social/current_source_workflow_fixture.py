"""Explicit current-schema workflow fixture with real retained county evidence.

Historical DDL fixtures stay separate. No unit authority marker, reader stub or
source verification replacement is installed here. The producer cache records
only which owned ingestion already ran; every observation is read afresh.
"""
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import UUID

import pytest
from sqlalchemy import select

from social.contracts import ApproveCommand
from social.generation.contracts import SourceObservation
from social.models import SocialControls, SocialPostTarget
from test_domain_support import call
from test_generation import configure, consume, evaluate, rule


class CurrentCountySource:
    def __init__(self, factory, directory):
        self.factory, self.directory = factory, directory
        self.productions = {}
        self.lock = Lock()

    def observation(self, version=1, value='123.45', *, report=False, **changes):
        from test_report_postgres import ingest
        from seeding.source_observations import (read_county_budget_record_ids,
            read_county_budget_observation, read_county_report_observation)
        key = (report, version)
        with self.lock:
            if key not in self.productions:
                year = 2023 + version if report else 2025
                job = ingest(self.factory, self.directory, year=year,
                    published=f'{year+1}-07-01', amount=value)
                record = read_county_budget_record_ids(self.factory, ingestion_id=job)[0]
                self.productions[key] = (value, job, record)
            previous, job, record = self.productions[key]
            if previous != value:
                raise ValueError('A test source version cannot change meaning')
        # Actual current reader and qualification; never return a cached source.
        reader = read_county_report_observation if report else read_county_budget_observation
        raw = reader(self.factory, record_id=record, ingestion_id=job)
        source = SourceObservation.model_validate(raw)
        if changes:
            # The render-rollback test deliberately injects an unresolved title;
            # it must fail before any witness or draft can be committed.
            if set(changes) != {'title'}:
                raise ValueError('Only the explicit unresolved-title control is supported')
            source = source.model_copy(update=changes)
        return source


@pytest.fixture
def current_source_engine(current_schema_pg, tmp_path):
    factory, engine = current_schema_pg
    engine.current_county_source = CurrentCountySource(factory, tmp_path)
    try:
        yield engine
    finally:
        del engine.current_county_source


def observation(engine, version=1, value='123.45', **changes):
    return engine.current_county_source.observation(version, value, **changes)


def current_rule(db, accounts, **changes):
    return rule(db, accounts, **changes)


def accepted_current_snapshot(db, a, monkeypatch, *, enable=True):
    """Real qualified sample; simulated offline operating outcome only."""
    from social.automation.contracts import OperatingEvidenceCommand, SnapshotCommand, PolicyControlsCommand
    from social.automation.service import AutomationService
    source = observation(db.get_bind().engine, report=True)
    a.capabilities_checked_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    db.commit()
    configure(db, [a])
    created = consume(db, source, backfill=True)
    sample = call(db, source, lambda s: s.detail(UUID(created['post_id'])))[1]
    policy = current_rule(db, [a])
    decision = evaluate(db, sample, policy)
    approval = ApproveCommand(expected_version=sample['version'], revision_id=sample['revision_id'],
        review_attestation={'facts_checked': True, 'sources_checked': True})
    call(db, approval, lambda s: s.approve(UUID(sample['id']), approval))
    target = db.scalar(select(SocialPostTarget))
    target.state, target.published_at, target.primary_remote_id = 'published', datetime.now(timezone.utc), 'inert-fixture-outcome'
    target.visibility_state, target.confirmation_kind = 'public', 'fixture-only'
    db.commit()
    body = OperatingEvidenceCommand(rule_id=policy['id'], rule_version=1, rule_hash=policy['definition_hash'],
        shadow_decision_ids=[decision['id']], evidence_url='https://example.test/owned-operating-fixture',
        evidence_sha256='e'*64, accuracy_accepted=True, reliability_accepted=True, corrections_reviewed=True,
        reason='Synthetic local contract outcome with qualified source, no live acceptance')
    evidence = call(db, body, lambda s: AutomationService(s).accept_operating_evidence(body))[1]
    body = SnapshotCommand(operating_evidence_id=evidence['id'], rule_id=policy['id'], rule_version=1,
        materiality_mode='new_reporting_release',
        rule_hash=policy['definition_hash'], valid_until=datetime.now(timezone.utc)+timedelta(days=1),
        reason='Synthetic local policy fixture with qualified current source')
    snapshot = call(db, body, lambda s: AutomationService(s).authorize_snapshot(body))[1]
    if enable:
        monkeypatch.setenv('SOCIAL_POLICY_AUTOMATION_ENABLED', 'true')
        cfg = db.get(SocialControls, 1)
        cfg.publishing_enabled = True
        db.commit()
        body = PolicyControlsCommand(expected_version=cfg.version, snapshot_id=snapshot['id'],
            auto_approve_enabled=True, auto_schedule_enabled=True, auto_publish_enabled=True,
            reason='Inert isolated fixture only')
        call(db, body, lambda s: AutomationService(s).set_controls(body))
    return snapshot, policy, evidence


def current_candidate(db, value='200', version=2):
    from unittest.mock import patch
    source = observation(db.get_bind().engine, version, value, report=True)
    with patch.dict('os.environ', {'SOCIAL_POLICY_AUTOMATION_ENABLED': 'false'}):
        created = consume(db, source)
    return call(db, source, lambda s: s.detail(UUID(created['post_id'])))[1]
