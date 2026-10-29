"""Actual qualified report writers and version-bound policy replay, offline."""
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import select
from test_b83_generation_postgres import pg
from test_report_postgres import queued_report, repository_gate
from social.models import SocialPost, SocialPostRevision, SocialPublication
from social.automation.models import AuthorizedPolicySnapshot
from social.automation.service import worker_gate, source_scope
from social.generation.contracts import SourceObservation
from native_worker_fixture import restricted
import pytest


def test_actual_national_report_writer_backfill_keeps_the_qualified_document_link(restricted,tmp_path,monkeypatch):
    from test_financial_copy_postgres import national_ingestion
    from test_native_financial_changes_postgres import enable
    from seeding.source_observations import read_native_report_record_ids, read_national_report_observation
    from social.generation.service import consume_observation, verify_generated_revision
    from test_domain_support import call
    from test_b83_generation_postgres import no_publication
    factory,_,_,_=restricted;enable(factory,monkeypatch)
    ingestion=national_ingestion(factory,tmp_path)
    records=read_native_report_record_ids(factory,ingestion_id=ingestion,domain='national_budget')
    assert len(records)==1
    source=SourceObservation.model_validate(read_national_report_observation(factory,record_id=records[0],ingestion_id=ingestion))
    with factory() as db:
        result=call(db,source,lambda svc:consume_observation(svc,source,backfill=True))[1]
        post=db.get(SocialPost,UUID(result['post_id']));revision=db.get(SocialPostRevision,post.current_revision_id)
        assert revision.generator_metadata['template_version']=='report-availability-v3'
        assert revision.document['master']['link']==source.report.document_url
        assert 'FY 2025/26' in revision.document['master']['text']
        assert 'publisher’s website' in revision.document['master']['text']
        verify_generated_revision(db,post,revision)
    no_publication(factory)


def test_new_report_copy_has_real_reviewed_policy_scope_and_current_worker_authority(pg,tmp_path,monkeypatch):
    factory,engine,account_id,publication_id,_=queued_report(pg,tmp_path,monkeypatch)
    with factory() as db:
        pub=db.get(SocialPublication,publication_id);rev=db.get(SocialPostRevision,pub.revision_id)
        source=SourceObservation.model_validate(rev.evidence_snapshot['source'])
        snapshot=db.get(AuthorizedPolicySnapshot,pub.policy_id)
        assert rev.generator_metadata['template_version']=='report-availability-v3'
        assert source_scope(source) in snapshot.snapshot['source_scopes']
        assert source_scope(source,template_version='report-availability-v1') not in snapshot.snapshot['source_scopes']
        assert 'explore the budget implementation report' in rev.document['master']['text']
        assert rev.document['master']['link']==source.report.document_url
        assert worker_gate(db.connection(),publication_id,account_id,'facebook',datetime.now(timezone.utc),public=True) is None
        assert repository_gate(db,engine,publication_id,account_id) is None


@pytest.mark.parametrize('old_version',['report-availability-v1','report-availability-v2'])
def test_accepted_report_policy_keeps_its_scope_after_upgrade(pg,tmp_path,monkeypatch,old_version):
    import social.generation.service as generation
    original=generation.generator_metadata
    with monkeypatch.context() as patch:
        def pinned(source, *, template_version=None):
            selected=template_version or (old_version if source.report else 'factual-v1')
            return original(source,template_version=selected)
        patch.setattr(generation,'generator_metadata',pinned)
        factory,engine,account_id,publication_id,_=queued_report(pg,tmp_path,monkeypatch)
    # New defaults are restored; replay the real immutable V1 authorization.
    with factory() as db:
        pub=db.get(SocialPublication,publication_id);rev=db.get(SocialPostRevision,pub.revision_id)
        source=SourceObservation.model_validate(rev.evidence_snapshot['source'])
        snapshot=db.get(AuthorizedPolicySnapshot,pub.policy_id)
        assert rev.generator_metadata['template_version']==old_version
        assert source_scope(source,template_version=old_version) in snapshot.snapshot['source_scopes']
        assert source_scope(source) not in snapshot.snapshot['source_scopes']
        assert rev.document['master']['link']==source.report.canonical_url
        assert ('Report available from' if old_version.endswith('v1') else 'explore the budget implementation report') in rev.document['master']['text']
        assert worker_gate(db.connection(),publication_id,account_id,'facebook',datetime.now(timezone.utc),public=True) is None
        assert repository_gate(db,engine,publication_id,account_id) is None
