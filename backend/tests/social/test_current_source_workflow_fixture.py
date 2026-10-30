"""Unmocked absent-authority and changed-source controls for the workflow lane."""
from uuid import UUID

import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from models import BudgetLine
from social.generation.service import verify_generated_revision
from social.generation.worker_authority import verify_worker_authority
from social.models import SocialPost, SocialPostRevision, SocialPublication, SocialPublishAttempt
from social.service import SocialError
from test_b83_generation_postgres import pg as current_schema_pg
from test_generation import configure, consume
from current_source_workflow_fixture import current_source_engine, observation


def test_current_workflow_requires_real_saved_authority(current_source_engine):
    source = observation(current_source_engine)
    with Session(current_source_engine, expire_on_commit=False) as db:
        configure(db)
        created = consume(db, source, backfill=True)
        post = db.get(SocialPost, UUID(created['post_id']))
        revision = db.get(SocialPostRevision, post.current_revision_id)
        assert revision.evidence_snapshot['worker_authority']
        verify_generated_revision(db, post, revision)
        with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
            verify_worker_authority(db, source.model_dump(mode='json'), None)
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0


def test_current_workflow_producer_cache_never_replaces_current_reader(current_source_engine):
    from seeding.source_observations import SourceObservationUnavailable
    source = observation(current_source_engine)
    with Session(current_source_engine, expire_on_commit=False) as db:
        configure(db)
        created = consume(db, source, backfill=True)
    factory = current_source_engine.current_county_source.factory
    with factory.begin() as db:
        db.get(BudgetLine, int(source.source_key.split(':')[1])).actual_spent += 1
    with pytest.raises(SourceObservationUnavailable):
        observation(current_source_engine)
    with factory() as db:
        post = db.get(SocialPost, UUID(created['post_id']))
        revision = db.get(SocialPostRevision, post.current_revision_id)
        with pytest.raises(SocialError, match='SOURCE_REVIEW_REQUIRED'):
            verify_generated_revision(db, post, revision)
        assert db.scalar(select(func.count()).select_from(SocialPublishAttempt)) == 0
        assert db.scalar(select(func.count()).select_from(SocialPublication)) == 0
