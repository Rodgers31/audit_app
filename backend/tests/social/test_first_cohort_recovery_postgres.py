"""Desired recovery semantics, owned real PG/source fixture; no live work."""
import pytest
from sqlalchemy import select,func
from models import Entity,Loan,IngestionJob
from social.generation.models import SourceCursor
from social.generation.service import consume_observation
from social.service import SocialService
from social.models import SocialPost,SocialPostRevision
from seeding.source_observations import read_pending_bills_financial_observation
from test_automatic_cohort_timeout_postgres import ingest_cohort,automatic,enabled
from test_b83_generation_postgres import pg,no_publication


def first_partial(factory,tmp_path,monkeypatch):
    import social.generation.integration as integration
    enabled(factory,monkeypatch)
    job=ingest_cohort(factory,tmp_path)
    original=integration.consume_committed_native_financial
    calls=0
    def stop_after_two_commits(*args,**kwargs):
        nonlocal calls
        result=original(*args,**kwargs);calls+=1
        if calls==3:raise integration.GenerationDeadlineExceeded('Owned first-cohort interruption before third commit')
        return result
    with monkeypatch.context() as patch:
        patch.setattr(integration,'consume_committed_native_financial',stop_after_two_commits)
        partial=automatic(factory,job)
    assert partial['state']=='failed' and partial['processed']==2 and partial['baselines']==2
    assert partial['drafts_created']==0 and not partial.get('execution_unverified')
    with factory() as db:
        root=db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        county=list(db.scalars(select(SourceCursor).where(~SourceCursor.source_key.endswith(':baseline'))))
        assert len(county)==2 and all(c.sequence==0 for c in county)
        assert db.scalar(select(func.count()).select_from(SocialPost))==0
        root_state=dict(root.report_state)
        known_keys={c.source_key for c in county}
        loans=list(db.scalars(select(Loan).order_by(Loan.id)))
        identities=[(r.id,db.get(Entity,r.entity_id).canonical_name) for r in loans]
    known=[]
    for record,name in identities:
        obs=read_pending_bills_financial_observation(factory,record_id=record,ingestion_id=job)
        if obs['source_key'] in known_keys:known.append((record,name))
    assert len(known)==2
    return job,partial,root_state,known,identities


@pytest.mark.parametrize('case',['unchanged','unchanged_with_backfill','known_change'])
def test_partial_first_cohort_new_job_does_not_invent_missing_county_changes(pg,tmp_path,monkeypatch,case):
    factory,_=pg
    first,partial,root_state,known,identities=first_partial(factory,tmp_path,monkeypatch)
    backfill=None
    if case=='unchanged_with_backfill':
        record=next(record for record,name in identities if name=='Nairobi County')
        obs=read_pending_bills_financial_observation(factory,record_id=record,ingestion_id=first)
        with factory.begin() as db:backfill=consume_observation(SocialService(db),obs,backfill=True)
        assert backfill['status']=='draft_created'
    with factory() as db:before_posts=db.scalar(select(func.count()).select_from(SocialPost))
    correction=known[0][1].removesuffix(' County') if case=='known_change' else None
    newer=ingest_cohort(factory,tmp_path,retained=True,correction=correction)
    outcome=automatic(factory,newer)
    with factory() as db:
        after_posts=db.scalar(select(func.count()).select_from(SocialPost))
        root=db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        root_after=dict(root.report_state)
        posts=list(db.scalars(select(SocialPost)))
        assert all(p.editorial_state=='pending_review' for p in posts)
        emitted=[]
        for post in posts:
            revision=db.get(SocialPostRevision,post.current_revision_id)
            emitted.append({'entity':revision.evidence_snapshot['source']['facts'][0]['entity'],'value':revision.evidence_snapshot['source']['facts'][0]['value'],'ingestion_id':revision.evidence_snapshot['source']['ingestion_id']})
    no_publication(factory)
    receipt={'case':case,'first_job':first,'newer_job':newer,'partial':partial,'prior_backfill':backfill,'root_before':root_state,'root_after':root_after,'known_baseline_entities':[x[1] for x in known],'correction':correction,'outcome':outcome,'posts_before':before_posts,'posts_after':after_posts,'emitted':emitted}
    expected=1 if case=='known_change' else 0
    assert outcome['state']=='completed'
    assert outcome['drafts_created']==expected,receipt
    assert after_posts==before_posts+expected,receipt


def test_only_complete_automatic_cohort_establishes_new_fact_detection(pg, tmp_path, monkeypatch):
    from social.generation.integration import maybe_generate_committed
    from seeding.source_observations import read_native_financial_record_ids
    from social.generation.preview import preview
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest_cohort(factory, tmp_path)
    ids = read_native_financial_record_ids(factory, ingestion_id=first, domain='pending_bills')
    subset = maybe_generate_committed(factory, record_ids=ids[:2], ingestion_id=first, domain='pending_bills')
    assert subset['state'] == 'unavailable' and subset['processed'] == 2 and subset['drafts_created'] == 0
    with factory() as db:
        root = db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        assert root.report_state['financial_baseline'] == 1
    complete = automatic(factory, first)
    assert complete['state'] == 'completed' and complete['baselines'] == 44 and complete['unchanged'] == 2
    with factory() as db:
        root = db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        assert root.report_state['financial_baseline'] == 2 and root.report_state['completed_count'] == 46
        assert root.evidence_version == first
    newer = ingest_cohort(factory, tmp_path, retained=True, include_nandi=True)
    with factory() as db:
        record = db.scalar(select(Loan.id).join(Entity).where(Entity.canonical_name == 'Nandi County'))
    decision = preview(factory, dict(domain='pending_bills', record_ids=[record], ingestion_id=newer, reports=False, backfill=False))
    assert decision['results'][0]['status'] == 'eligible_change'
    changed = automatic(factory, newer)
    assert changed['state'] == 'completed' and changed['drafts_created'] == 1 and changed['unchanged'] == 46
    again = automatic(factory, newer)
    assert again['state'] == 'completed' and again['drafts_created'] == 0 and again['unchanged'] == 47
    with factory() as db:
        posts = list(db.scalars(select(SocialPost)))
        assert len(posts) == 1 and posts[0].editorial_state == 'pending_review'
        revision = db.get(SocialPostRevision, posts[0].current_revision_id)
        assert revision.evidence_snapshot['source']['facts'][0]['entity'] == 'Nandi County'
    no_publication(factory)


@pytest.mark.parametrize('bad_count', [True, 0, -1, 1001, 46.0, '46', None])
def test_malformed_completed_cohort_marker_cannot_enable_drafts(pg, tmp_path, monkeypatch, bad_count):
    from sqlalchemy.orm.attributes import flag_modified
    factory, _ = pg
    enabled(factory, monkeypatch)
    first = ingest_cohort(factory, tmp_path)
    assert automatic(factory, first)['baselines'] == 46
    with factory.begin() as db:
        root = db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        root.report_state = {**root.report_state, 'completed_count': bad_count}
        # ORM JSON equality treats 46.0 == 46; persist the intended hostile type.
        flag_modified(root, 'report_state')
    newer = ingest_cohort(factory, tmp_path, retained=True, correction='Nairobi')
    result = automatic(factory, newer)
    assert result['state'] != 'completed' and result['drafts_created'] == 0
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)


@pytest.mark.parametrize('change', ['withdrawn', 'numeric_mutation', 'wrong_cursor_identity', 'receipt_mutation', 'entity_rename'])
def test_automatic_completion_refuses_inputs_changed_after_last_record(pg, tmp_path, monkeypatch, change):
    import social.generation.integration as integration
    from models import SourceDocument, DocumentStatus, Extraction
    factory, _ = pg
    enabled(factory, monkeypatch)
    job = ingest_cohort(factory, tmp_path)
    original = integration._complete_financial_cohort
    def before_completion(_factory, *args, **kwargs):
        with factory.begin() as db:
            if change == 'withdrawn':
                db.scalar(select(SourceDocument)).status = DocumentStatus.ARCHIVED
            elif change == 'numeric_mutation':
                db.scalar(select(Loan)).outstanding += 1
            elif change == 'wrong_cursor_identity':
                cursor = db.scalar(select(SourceCursor).where(~SourceCursor.source_key.endswith(':baseline')))
                cursor.source_key = 'cob:financial:pending_bills:' + '0' * 64
            elif change == 'entity_rename':
                record = db.scalar(select(Loan))
                db.get(Entity, record.entity_id).canonical_name += ' changed after qualification'
            else:
                receipt = db.scalar(select(Extraction).where(Extraction.extractor == 'pdf-receipt-v1'))
                assert receipt is not None
                receipt.extracted_json = {**receipt.extracted_json, 'owned_changed_after_qualification': True}
        return original(_factory, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(integration, '_complete_financial_cohort', before_completion)
        result = automatic(factory, job)
    assert result['state'] != 'completed' and result['processed'] == 46 and result['baselines'] == 46
    assert result['drafts_created'] == 0 and not result.get('execution_unverified')
    with factory() as db:
        root = db.scalar(select(SourceCursor).where(SourceCursor.source_key.endswith(':baseline')))
        assert root.report_state['financial_baseline'] == 1
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)


@pytest.mark.parametrize('change', ['source_key', 'input_hash', 'reconstructed', 'instance_override', 'subclass_override'])
def test_mutated_or_reconstructed_cohort_witness_rolls_back_record(pg, tmp_path, monkeypatch, change):
    from copy import deepcopy
    import social.generation.integration as integration
    from seeding.financial_cohort_witness import FinancialCohortWitness
    factory, _ = pg
    enabled(factory, monkeypatch)
    job = ingest_cohort(factory, tmp_path)
    original = integration.consume_committed_native_financial
    def tampered(*args, **kwargs):
        result = original(*args, **kwargs)
        witness = result['_cohort_witness']
        if change == 'source_key':
            witness.value['source_key'] += 'changed'
        elif change == 'input_hash':
            table = next(iter(witness.value['inputs']))
            identity = next(iter(witness.value['inputs'][table]))
            witness.value['inputs'][table][identity] = '0' * 64
        else:
            class PretendWitness(FinancialCohortWitness):
                def intact(self):
                    return True
            forged = object.__new__(PretendWitness if change == 'subclass_override' else FinancialCohortWitness)
            forged.value = deepcopy(witness.value)
            if change == 'instance_override':
                forged.intact = lambda: True
            result['_cohort_witness'] = forged
        return result
    with monkeypatch.context() as patch:
        patch.setattr(integration, 'consume_committed_native_financial', tampered)
        outcome = automatic(factory, job)
    assert outcome['state'] != 'completed'
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(SourceCursor)) == 0
        assert db.scalar(select(func.count()).select_from(SocialPost)) == 0
    no_publication(factory)
