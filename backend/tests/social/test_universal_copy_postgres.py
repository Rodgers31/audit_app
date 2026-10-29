"""Actual qualified report writers and version-bound policy replay, offline."""
from datetime import datetime, timezone
from sqlalchemy import select
from test_b83_generation_postgres import pg
from test_report_postgres import queued_report, repository_gate
from social.models import SocialPost, SocialPostRevision, SocialPublication
from social.automation.models import AuthorizedPolicySnapshot
from social.automation.service import worker_gate, source_scope
from social.generation.contracts import SourceObservation


def test_new_report_copy_has_real_reviewed_policy_scope_and_current_worker_authority(pg,tmp_path,monkeypatch):
    factory,engine,account_id,publication_id,_=queued_report(pg,tmp_path,monkeypatch)
    with factory() as db:
        pub=db.get(SocialPublication,publication_id);rev=db.get(SocialPostRevision,pub.revision_id)
        source=SourceObservation.model_validate(rev.evidence_snapshot['source'])
        snapshot=db.get(AuthorizedPolicySnapshot,pub.policy_id)
        assert rev.generator_metadata['template_version']=='report-availability-v2'
        assert source_scope(source) in snapshot.snapshot['source_scopes']
        assert source_scope(source,template_version='report-availability-v1') not in snapshot.snapshot['source_scopes']
        assert 'explore the budget implementation report' in rev.document['master']['text']
        assert worker_gate(db.connection(),publication_id,account_id,'facebook',datetime.now(timezone.utc),public=True) is None
        assert repository_gate(db,engine,publication_id,account_id) is None


def test_accepted_v1_report_policy_keeps_its_scope_and_does_not_accept_v2_after_upgrade(pg,tmp_path,monkeypatch):
    import social.generation.service as generation
    original=generation.generator_metadata
    with monkeypatch.context() as patch:
        def pinned(source, *, template_version=None):
            selected=template_version or ('report-availability-v1' if source.report else 'factual-v1')
            return original(source,template_version=selected)
        patch.setattr(generation,'generator_metadata',pinned)
        factory,engine,account_id,publication_id,_=queued_report(pg,tmp_path,monkeypatch)
    # New defaults are restored; replay the real immutable V1 authorization.
    with factory() as db:
        pub=db.get(SocialPublication,publication_id);rev=db.get(SocialPostRevision,pub.revision_id)
        source=SourceObservation.model_validate(rev.evidence_snapshot['source'])
        snapshot=db.get(AuthorizedPolicySnapshot,pub.policy_id)
        assert rev.generator_metadata['template_version']=='report-availability-v1'
        assert source_scope(source,template_version='report-availability-v1') in snapshot.snapshot['source_scopes']
        assert source_scope(source) not in snapshot.snapshot['source_scopes']
        assert 'Report available from' in rev.document['master']['text']
        assert worker_gate(db.connection(),publication_id,account_id,'facebook',datetime.now(timezone.utc),public=True) is None
        assert repository_gate(db,engine,publication_id,account_id) is None
