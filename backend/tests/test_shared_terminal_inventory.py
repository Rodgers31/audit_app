"""Strict result types and separately fenced terminal inventory acceptance.

PostgreSQL cases require the existing explicit owned CLI fixture URL. Default
unit runs retain SQLite/model/guard coverage and skip only those PG cases.
"""
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, 'sqlite')
def sqlite_jsonb(*args, **kwargs):
    return 'TEXT'

from models import EtlDispatchCommand, EtlDispatchDomain, IngestionJob, IngestionStatus, SeedingDomainClaim
from seeding.exclusion import DomainExecution, DomainOwnershipError, dispatch_scope, enter_domain, enter_domains, _coherent_terminal_job
from seeding.types import DomainRunResult
from test_cli_admin_result_postgres import pg, accepted

PLAN = {'mode':'discovery_only','extraction':'not_requested','publication':'not_requested'}
requires_pg = pytest.mark.skipif(
    not os.environ.get('CLI_RESULT_DATABASE_URL'),
    reason='Explicit isolated PostgreSQL fixture required',
)

BAD_COUNTS=[pytest.param(v,id=name) for name,v in [
    ('true',True),('false',False),('string-one','1'),('string-zero','0'),
    ('float-one',1.0),('negative',-1),('overflow',2147483648),('nan',float('nan')),
    ('posinf',float('inf')),('neginf',float('-inf')),('none',None),('list',[]),('object',{})]]

@pytest.mark.parametrize('field',['items_processed','items_created','items_updated'])
@pytest.mark.parametrize('value',BAD_COUNTS)
def test_constructor_cannot_erase_invalid_counter_type_or_bounds(field,value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DomainRunResult(domain='audits',**{field:value})

@pytest.mark.parametrize('value',[pytest.param(v,id=name) for name,v in [
    ('int-one',1),('int-zero',0),('string-true','true'),('string-false','false'),
    ('float-one',1.0),('none',None),('list',[]),('object',{})]])
def test_constructor_requires_actual_dry_run_boolean(value):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DomainRunResult(domain='audits',dry_run=value)

@pytest.mark.parametrize('counts',[(0,0,0),(1,0,0),(2147483647,2147483647,0)])
@pytest.mark.parametrize('dry_run',[False,True])
def test_constructor_preserves_exact_valid_counts(counts,dry_run):
    result=DomainRunResult(domain='audits',items_processed=counts[0],items_created=counts[1],items_updated=counts[2],dry_run=dry_run)
    assert (result.items_processed,result.items_created,result.items_updated)==counts
    assert all(type(v) is int for v in (result.items_processed,result.items_created,result.items_updated))
    assert result.dry_run is dry_run

# ORM-free direct guard calls enumerate hostile in-memory shapes that a DB
# integer column may coerce or reject before the application sees them.
class ClockSession:
    def get_bind(self):return SimpleNamespace(dialect=SimpleNamespace(name='sqlite'))

def memory_job(**changes):
    now=datetime.now(timezone.utc)
    data=dict(status=IngestionStatus.COMPLETED,domain='audits',dry_run=False,
              items_processed=2,items_created=1,items_updated=0,errors=[],meta={},
              started_at=now,finished_at=now)
    data.update(changes)
    return SimpleNamespace(**data)

@pytest.mark.parametrize('field',['items_processed','items_created','items_updated'])
@pytest.mark.parametrize('value',BAD_COUNTS)
def test_direct_terminal_guard_refuses_hostile_untyped_counters(field,value):
    job=memory_job(**{field:value})
    assert _coherent_terminal_job(ClockSession(),job,job.started_at) is None

TERMINALS=[
    pytest.param('audits',False,IngestionStatus.COMPLETED,(0,0,0),[],{},False,id='hollow-completed'),
    pytest.param('audits',False,IngestionStatus.COMPLETED,(1,1,1),[],{},False,id='overcount-completed'),
    pytest.param('audits',False,IngestionStatus.COMPLETED,(2,0,0),[],{},True,id='positive-unchanged'),
    pytest.param('audits',False,IngestionStatus.COMPLETED,(2,1,1),[],{},True,id='positive-changes'),
    pytest.param('audits',True,IngestionStatus.COMPLETED,(0,0,0),[],{'dry_run_plan':PLAN},True,id='exact-discovery-preview'),
    pytest.param('audits',False,IngestionStatus.COMPLETED,(0,0,0),[],{'dry_run_plan':PLAN},False,id='nondry-discovery-plan'),
    pytest.param('audits',True,IngestionStatus.COMPLETED,(0,0,0),[],{'dry_run_plan':{**PLAN,'extra':True}},False,id='extended-discovery-plan'),
    pytest.param('population',True,IngestionStatus.COMPLETED,(0,0,0),[],{'dry_run_plan':PLAN},False,id='wrong-domain-discovery-plan'),
    pytest.param('audits',False,IngestionStatus.FAILED,(0,0,0),['known failure'],{},True,id='known-zero-failure'),
    pytest.param('audits',False,IngestionStatus.COMPLETED_WITH_ERRORS,(0,0,0),['fixture unavailable'],{'source_mode':'fixture'},True,id='known-zero-fixture-cwe'),
    pytest.param('audits',False,IngestionStatus.COMPLETED_WITH_ERRORS,(2,1,0),['known partial error'],{},True,id='positive-partial-cwe'),
]

@pytest.mark.parametrize('domain,dry_run,status,counts,errors,meta,allowed',TERMINALS)
@requires_pg
def test_native_acknowledgment_requires_coherent_terminal_inventory(pg,domain,dry_run,status,counts,errors,meta,allowed):
    _client,factory,_engine,_generation=pg
    owner=enter_domain(factory,domain,dry_run)
    try:
        with factory.begin() as db:
            now=datetime.now(timezone.utc)
            job=IngestionJob(domain=domain,dry_run=dry_run,status=status,started_at=now,finished_at=now,
                items_processed=counts[0],items_created=counts[1],items_updated=counts[2],errors=errors,
                meta={**meta,'seeding_claim_id':str(owner.identity)})
            db.add(job)
            db.flush()
            job_id=job.id
        if allowed:
            owner.acknowledge(job_id)
        else:
            with pytest.raises(DomainOwnershipError,match='Terminal observation unverified'):
                owner.acknowledge(job_id)
        with factory() as db:
            stored=db.get(SeedingDomainClaim,owner.identity)
            assert (stored.returned_at is not None) is allowed
            assert (stored.released_at is not None) is allowed
            assert stored.job_id==(job_id if allowed else None)
    finally:owner.close()

@pytest.mark.parametrize('fault',['old-start','future-finish','reversed','wrong-tag'])
@requires_pg
def test_native_acknowledgment_preserves_owner_and_timestamp_checks(pg,fault):
    _client,factory,_engine,_generation=pg
    owner=enter_domain(factory,'audits',False)
    try:
        with factory.begin() as db:
            now=datetime.now(timezone.utc)
            job=IngestionJob(domain='audits',dry_run=False,status=IngestionStatus.COMPLETED,
                started_at=now-timedelta(seconds=10) if fault=='old-start' else now,
                finished_at=now+timedelta(seconds=10) if fault=='future-finish' else now-timedelta(seconds=1) if fault=='reversed' else now,
                items_processed=2,items_created=0,items_updated=0,errors=[],
                meta={'seeding_claim_id':str(uuid4() if fault=='wrong-tag' else owner.identity)})
            db.add(job)
            db.flush()
            job_id=job.id
        with pytest.raises(DomainOwnershipError,match='Terminal observation unverified'):
            owner.acknowledge(job_id)
        with factory() as db:
            stored=db.get(SeedingDomainClaim,owner.identity)
            assert stored.returned_at is None and stored.released_at is None and stored.job_id is None
    finally:owner.close()

FINISH_CASES=[t for t in TERMINALS if t.values[0]=='audits']

@pytest.mark.parametrize('domain,dry_run,status,counts,errors,meta,allowed',FINISH_CASES)
@requires_pg
def test_finish_rechecks_inventory_after_genuine_entry_and_acknowledgment(pg,domain,dry_run,status,counts,errors,meta,allowed):
    client,factory,_engine,generation=pg
    # Real mounted API acceptance and claim. The command is then genuinely
    # entered; no child worker, subprocess adapter or source handler is started.
    if not dry_run:
        command_id,token,_key=accepted(pg)
    else:
        response=client.post('/api/v1/admin/etl/trigger/oag',json={'dry_run':True,'dispatch_generation':str(generation)},
            headers={'Authorization':'Bearer fixture-admin','Idempotency-Key':str(uuid4())})
        assert response.status_code==202,response.text
        command_id=UUID(response.json()['command']['id'])
        from admin_etl_dispatch_worker import claim
        selected,token=claim(factory,generation)
        assert selected==command_id
    with factory.begin() as db:db.get(EtlDispatchCommand,command_id).execution_started=True
    owner=DomainExecution(factory,'audits',token,command_id,generation)
    owner.open()
    try:
        with dispatch_scope(owner):
            entering=enter_domain(factory,'audits',dry_run)
            with factory.begin() as db:
                now=datetime.now(timezone.utc)
                job=IngestionJob(domain='audits',dry_run=dry_run,status=IngestionStatus.COMPLETED,
                    started_at=now,finished_at=now,items_processed=2,items_created=1,items_updated=0,errors=[],
                    meta={'seeding_claim_id':str(token),'dispatch_command_id':str(command_id),'dispatch_claim_token':str(token)})
                db.add(job)
                db.flush()
                job_id=job.id
            entering.acknowledge(job_id)
    finally:owner.close()
    # Mutate durable observation after a real valid acknowledgment so that a
    # fixed acknowledgment cannot mask an independently vulnerable finish.
    with factory.begin() as db:
        job=db.get(IngestionJob,job_id)
        job.status=status
        job.items_processed,job.items_created,job.items_updated=counts
        job.errors=errors
        job.meta={**job.meta,**meta}
    from admin_etl_dispatch_worker import finish
    exit_code=0 if status==IngestionStatus.COMPLETED else 1
    result=finish(factory,generation,command_id,token,exit_code)
    assert result is allowed
    with factory() as db:
        command=db.get(EtlDispatchCommand,command_id)
        claim_row=db.get(SeedingDomainClaim,token)
        domain_row=db.get(EtlDispatchDomain,'audits')
        expected_status=('completed' if exit_code==0 else 'failed') if allowed else 'interrupted'
        assert command.status==expected_status
        assert claim_row.returned_at is not None
        assert (claim_row.released_at is not None) is allowed
        assert domain_row.command_id==(None if allowed else command_id)


@requires_pg
def test_reference_group_zero_receipt_remains_separate_from_source_ingestion(pg):
    _client,factory,_engine,_generation=pg
    group=enter_domains(factory,('bootstrap_reference_data','audits'),'bootstrap_reference_data')
    try:
        with factory.begin() as db:
            now=datetime.now(timezone.utc)
            job=IngestionJob(domain='bootstrap_reference_data',dry_run=False,status=IngestionStatus.COMPLETED,
                started_at=now,finished_at=now,errors=[],meta={'seeding_claim_ids':group.claim_ids})
            db.add(job)
            db.flush()
            job_id=job.id
        group.acknowledge(job_id)
        with factory() as db:
            claims=db.scalars(select(SeedingDomainClaim)).all()
            assert len(claims)==2
            assert all(c.job_id==job_id and c.returned_at is not None and c.released_at is not None for c in claims)
    finally:group.close()

# These use the existing real CLI harness, not a copied implementation.
from test_cli_result_truth import db as cli_db, invoke as invoke_cli

@pytest.mark.parametrize('bypass',['model_construct','model_copy','assignment'])
@pytest.mark.parametrize('field,value',[
    ('items_processed',True),('items_created','1'),('items_updated',1.0),
    ('items_processed',2147483648),('dry_run',0),
])
def test_bypassed_models_are_revalidated_by_actual_cli(cli_db,monkeypatch,bypass,field,value):
    from models import AdminAuditLog
    def handler(session,**_kwargs):
        session.add(AdminAuditLog(actor_id='fixture',action='bypass.effect',payload={}))
        session.flush()
        if bypass=='model_construct':
            data={'domain':'population','items_processed':2,field:value}
            return DomainRunResult.model_construct(**data)
        result=DomainRunResult(domain='population',items_processed=2)
        if bypass=='model_copy':return result.model_copy(update={field:value})
        setattr(result,field,value)
        return result
    assert invoke_cli(monkeypatch,handler)==1
    with cli_db() as db:
        job=db.scalars(select(IngestionJob)).one()
        assert job.status==IngestionStatus.FAILED
        assert (job.items_processed,job.items_created,job.items_updated)==(0,0,0)
        assert 'Invalid domain result' in job.errors[0]
        assert db.query(AdminAuditLog).count()==0
        claim_row=db.scalars(select(SeedingDomainClaim)).one()
        assert claim_row.returned_at is not None and claim_row.released_at is not None

@pytest.mark.parametrize('status',[IngestionStatus.FAILED,IngestionStatus.COMPLETED_WITH_ERRORS])
@pytest.mark.parametrize('counts',[(0,1,0),(1,1,1)])
@requires_pg
def test_non_success_terminal_counts_still_cannot_exceed_inventory(pg,status,counts):
    _client,factory,_engine,_generation=pg
    owner=enter_domain(factory,'audits',False)
    try:
        with factory.begin() as db:
            now=datetime.now(timezone.utc)
            job=IngestionJob(domain='audits',dry_run=False,status=status,started_at=now,finished_at=now,
                items_processed=counts[0],items_created=counts[1],items_updated=counts[2],errors=['known error'],
                meta={'seeding_claim_id':str(owner.identity)})
            db.add(job)
            db.flush()
            job_id=job.id
        with pytest.raises(DomainOwnershipError,match='Terminal observation unverified'):
            owner.acknowledge(job_id)
        with factory() as db:
            claim_row=db.get(SeedingDomainClaim,owner.identity)
            assert claim_row.returned_at is None and claim_row.released_at is None
    finally:owner.close()

@pytest.mark.parametrize('errors',[None,'failed',[True],[1],[''],['   '],{}])
@pytest.mark.parametrize('status',[IngestionStatus.FAILED,IngestionStatus.COMPLETED_WITH_ERRORS])
def test_direct_terminal_guard_refuses_malformed_error_shapes(status,errors):
    job=memory_job(status=status,errors=errors,items_processed=0,items_created=0)
    assert _coherent_terminal_job(ClockSession(),job,job.started_at) is None

@requires_pg
def test_legacy_synchronous_scope_keeps_ownership_only_zero_receipt_contract(pg):
    from etl.writer_ownership import LEGACY_DOMAINS, writer_scope
    _client,factory,engine,_generation=pg
    with writer_scope(engine) as scope:
        assert len(scope.executions)==len(LEGACY_DOMAINS)
    with factory() as db:
        jobs=db.scalars(select(IngestionJob)).all()
        claims=db.scalars(select(SeedingDomainClaim)).all()
        assert {j.domain for j in jobs}==set(LEGACY_DOMAINS)
        assert len(claims)==len(LEGACY_DOMAINS)
        assert all(j.status==IngestionStatus.COMPLETED and j.dry_run is False and
            (j.items_processed,j.items_created,j.items_updated)==(0,0,0) and j.errors==[] and
            j.meta['writer']=='legacy_etl' and j.meta['counts_scope']=='ownership_only' for j in jobs)
        assert all(c.returned_at is not None and c.released_at is not None and c.job_id is not None for c in claims)

@pytest.mark.parametrize('fault',['wrong-writer','wrong-scope','nonzero','errors'])
@requires_pg
def test_legacy_ownership_zero_exception_does_not_certify_wrong_scope_or_inventory(pg,fault):
    from etl.writer_ownership import LEGACY_DOMAINS, acquire_scope
    _client,factory,engine,_generation=pg
    scope=acquire_scope(engine)
    try:
        with factory.begin() as db:
            job=db.get(IngestionJob,scope.jobs['audits'])
            if fault=='wrong-writer':job.meta={**job.meta,'writer':'ordinary_native'}
            if fault=='wrong-scope':job.meta={**job.meta,'counts_scope':'source_ingestion'}
            if fault=='nonzero':job.items_created=1
            # _finish supplies [] on success, so malformed errors must be placed
            # after its real persistence and before the actual ack boundary.
        if fault=='errors':
            original=scope._acknowledge_all
            def corrupt_then_ack():
                with factory.begin() as db:db.get(IngestionJob,scope.jobs['audits']).errors=['unexpected']
                original()
            scope._acknowledge_all=corrupt_then_ack
        with pytest.raises(DomainOwnershipError,match='Legacy terminal observation unverified'):
            scope.finish()
        with factory() as db:
            rows=db.scalars(select(SeedingDomainClaim)).all()
            assert len(rows)==len(LEGACY_DOMAINS)
            assert all(c.returned_at is None and c.released_at is None and c.job_id is None for c in rows)
    finally:scope.close()

@pytest.mark.parametrize('domain,meta',[
    ('audits',{'writer':'legacy_etl','counts_scope':'ownership_only'}),
    ('bootstrap_reference_data',{'seeding_claim_ids':{}}),
])
@requires_pg
def test_single_native_owner_cannot_invent_an_ownership_only_scope_exception(pg,domain,meta):
    _client,factory,_engine,_generation=pg
    owner=enter_domain(factory,domain,False)
    try:
        with factory.begin() as db:
            now=datetime.now(timezone.utc)
            job=IngestionJob(domain=domain,status=IngestionStatus.COMPLETED,dry_run=False,
                started_at=now,finished_at=now,errors=[],meta={**meta,'seeding_claim_id':str(owner.identity)})
            db.add(job)
            db.flush()
            job_id=job.id
        with pytest.raises(DomainOwnershipError,match='Terminal observation unverified'):
            owner.acknowledge(job_id)
        with factory() as db:
            claim_row=db.get(SeedingDomainClaim,owner.identity)
            assert claim_row.returned_at is None and claim_row.released_at is None
    finally:owner.close()

