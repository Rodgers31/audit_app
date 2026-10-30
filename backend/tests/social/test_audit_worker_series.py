"""Restricted-login native digest views enforce the selected audit head.

Owned SQL/PDF fixtures only: no queue/provider/upload or worker starts. The
snapshot stays owner-only; current-view checks use the actual restricted login.
"""
from copy import deepcopy
import json

import pytest
from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

from models import IngestionJob
from native_worker_fixture import restricted
from seeding.native_report_observations import read_native_report_observation
from social.generation.contracts import SourceObservation
from social.generation.worker_authority import capture_worker_authority,verify_worker_authority
from social.service import SocialError
from test_audit_report_editions import persist_sequence
from test_b83_generation_postgres import pg,no_publication


CURRENT='public.social_native_source_authority'
SNAPSHOT=CURRENT+'_snapshot'


def fingerprint(engine,view,record,job,domain='audits'):
    assert view in {CURRENT,SNAPSHOT}
    with engine.begin() as conn:
        return conn.execute(text('SELECT authority_fingerprint FROM '+view+
            " WHERE source_kind='report' AND native_domain=:domain AND record_id=:record AND ingestion_id=:job"),
            {'domain':domain,'record':record,'job':job}).scalars().all()


def replace_series(factory,job,series):
    with factory.begin() as db:
        row=db.get(IngestionJob,job);metadata=deepcopy(row.meta)
        if series is ...:metadata.pop('native_report_series',None)
        else:metadata['native_report_series']=series
        row.meta=metadata;flag_modified(row,'meta');db.flush();db.refresh(row)
        assert json.dumps(row.meta,sort_keys=True)==json.dumps(metadata,sort_keys=True)


def captured(factory,record,job,domain='audits'):
    value=SourceObservation.model_validate(read_native_report_observation(factory,
        record_id=record,ingestion_id=job,domain=domain)).model_dump(mode='json')
    with factory.begin() as db:witness=capture_worker_authority(db,value)
    assert witness is not None
    return value,witness


@pytest.fixture
def audit_sources(restricted,tmp_path):
    factory,owner,worker,role=restricted
    job,refused=persist_sequence(factory,tmp_path,[
        ('https://www.oagkenya.go.ke/national-government-older.pdf',2025,'2025-07-10',False),
        ('https://www.oagkenya.go.ke/national-government-newer.pdf',2026,'2026-07-10',False)])
    assert not refused
    with factory() as db:meta=deepcopy(db.get(IngestionJob,job).meta)
    scope,head=next(iter(meta['native_report_series'].items()))
    old=next(record for record in meta['native_report_records']['audits']if record!=head)
    # Mint history only while it is explicitly selected; restoring the current
    # head models a stored legacy witness or a changed authority map.
    replace_series(factory,job,{scope:old})
    old_source,old_witness=captured(factory,old,job)
    replace_series(factory,job,{scope:head})
    source,witness=captured(factory,head,job)
    return factory,owner,worker,role,job,scope,head,old,source,witness,old_source,old_witness


@pytest.mark.parametrize('view',[CURRENT,SNAPSHOT])
def test_worker_digest_views_exclude_unselected_audit_receipt(audit_sources,view):
    factory,owner,worker,_,job,_,head,old,source,witness,_,_=audit_sources
    engine=worker if view==CURRENT else owner
    assert fingerprint(engine,view,head,job)==[witness['fingerprint']]
    with worker.begin() as conn:assert verify_worker_authority(conn,source,witness)is None
    assert fingerprint(engine,view,old,job)==[]
    no_publication(factory)


def test_stored_audit_witness_retires_when_its_head_is_unselected(audit_sources):
    factory,_,worker,_,_,_,_,_,_,_,source,witness=audit_sources
    with worker.begin() as conn:
        with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
            verify_worker_authority(conn,source,witness)
    no_publication(factory)


@pytest.mark.parametrize('case',['missing','null','array','boolean','null-head','bool-head',
    'float-head','string-head','zero-head','negative-head','foreign-head','foreign-scope','uppercase-scope'])
def test_bad_audit_series_has_no_worker_authority(audit_sources,case):
    factory,owner,worker,_,job,scope,head,_,source,witness,_,_=audit_sources
    if case=='missing':series=...
    elif case in {'null','array','boolean'}:series={'null':None,'array':[],'boolean':True}[case]
    elif case=='foreign-scope':series={'f'*32:head}
    elif case=='uppercase-scope':series={scope.upper():head}
    else:series={scope:{'null-head':None,'bool-head':True,'float-head':float(head),
        'string-head':str(head),'zero-head':0,'negative-head':-1,'foreign-head':head+1000}[case]}
    replace_series(factory,job,series)
    assert fingerprint(worker,CURRENT,head,job)==[]
    assert fingerprint(owner,SNAPSHOT,head,job)==[]
    with worker.begin() as conn:
        with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
            verify_worker_authority(conn,source,witness)
    no_publication(factory)


def test_entire_audit_series_map_is_a_stored_witness_dependency(audit_sources):
    factory,owner,worker,_,job,scope,head,old,source,witness,_,_=audit_sources
    replace_series(factory,job,{scope:head,'f'*32:old})
    current=fingerprint(worker,CURRENT,head,job)
    assert len(current)==1 and current!=[witness['fingerprint']]
    assert fingerprint(owner,SNAPSHOT,head,job)==current
    with worker.begin() as conn:
        with pytest.raises(SocialError,match='SOURCE_REVIEW_REQUIRED'):
            verify_worker_authority(conn,source,witness)
    no_publication(factory)


@pytest.mark.parametrize('domain',['national_budget','revenue_by_source','pending_bills'])
def test_other_native_report_fingerprints_keep_existing_dependency_scope(restricted,tmp_path,domain):
    factory,owner,worker,_=restricted
    if domain=='pending_bills':
        from test_native_publisher_postgres import ingest
        job,record=ingest(factory,tmp_path)
    else:
        from test_b86_native_postgres import ingest
        job,record=ingest(factory,tmp_path,domain=domain,
            url='https://cob.go.ke/native-annual.pdf'if domain=='national_budget'else 'https://www.kra.go.ke/news-center/press-release/owned-release',
            published='2025-07-10'if domain=='national_budget'else '10/07/2025')
    source,witness=captured(factory,record,job,domain)
    with factory() as db:series=deepcopy(db.get(IngestionJob,job).meta['native_report_series'])
    replace_series(factory,job,{**series,'f'*32:record})
    assert fingerprint(worker,CURRENT,record,job,domain)==[witness['fingerprint']]
    assert fingerprint(owner,SNAPSHOT,record,job,domain)==[witness['fingerprint']]
    with worker.begin() as conn:assert verify_worker_authority(conn,source,witness)is None
    no_publication(factory)


def test_snapshot_view_stays_private_to_owner(restricted):
    _,_,worker,_=restricted
    with pytest.raises(Exception) as error:
        with worker.begin() as conn:conn.execute(text('SELECT * FROM '+SNAPSHOT+' LIMIT 1'))
    assert error.value.orig.pgcode=='42501'
