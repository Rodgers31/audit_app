"""Explicit loopback-only repeatable result measurement. No production queries."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests/egress'),str(ROOT/'backend/tests/social')]

from harness import isolated_engine, local_url, seed_country
from sqlalchemy.orm import Session


def measure_stats(dsn):
    from test_compact_ingestion_stats import seed_jobs
    from routers.admin import get_ingestion_stats
    with isolated_engine(dsn) as (engine,probe):
        seed_jobs(engine)
        with Session(engine) as db,probe.capture():
            result=asyncio.run(get_ingestion_stats(days=30,db=db))
        return {**probe.summary(probe.selected('ingestion_jobs')),
                'response_total_jobs':result.total_jobs,'response_domains':len(result.domains)}


def measure_writers(dsn):
    from test_source_document_reads import WRITERS,source_rows
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    report={}
    for name,writer,records_fn in WRITERS:
        with isolated_engine(dsn) as (engine,probe):
            country_id,_=seed_country(engine)
            records=records_fn()
            source_rows(engine,records,country_id)
            with Session(engine) as db,probe.capture():
                stats=writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
                db.flush()
                db.commit()
            assert not stats.errors
            report[name]={**probe.summary(probe.selected('source_documents')),
                          'processed_records':stats.processed,'created_records':stats.created}
    return report


def measure_worker(dsn):
    from social.worker.config import WorkerConfig
    from social.worker.repository import QueueRepository
    from social.worker.runner import SocialWorker
    from social.contracts import OperationResult
    from test_queue_postgres import FakeAdapter,run_claim,seed
    result={}
    worker_dsn=local_url(dsn).render_as_string(hide_password=False)
    with isolated_engine(dsn,social=True) as (engine,probe):
        repo=QueueRepository(engine,WorkerConfig(worker_dsn),uuid4())
        with probe.capture():
            repo.recover_expired()
            assert repo.claim_due(2)==[]
            assert repo.next_due_delay(30)==30
        result['idle_scan']=probe.summary()
        with probe.capture():
            repo.heartbeat(state='idle',active_claims=0,scanned=True)
        result['idle_heartbeat']=probe.summary()
        seed(engine)
        fake=FakeAdapter()
        with probe.capture():
            run_claim(repo,fake)
        result['one_fake_publication']=probe.summary()
        assert fake.calls==1
        result['pool_size']=engine.pool.size()
        result['pool_max_overflow']=engine.pool._max_overflow
    with isolated_engine(dsn,social=True) as (engine,probe):
        repo=QueueRepository(engine,WorkerConfig(worker_dsn),uuid4())
        seed(engine,count=2)
        async def two_slots():
            both_started=asyncio.Event()
            active=0
            peak=0
            async def gate(operation):
                nonlocal active,peak
                active+=1
                peak=max(peak,active)
                if active==2:
                    both_started.set()
                await asyncio.wait_for(both_started.wait(),timeout=3)
                active-=1
            fake=FakeAdapter(gate=gate,results=[OperationResult(outcome='confirmed_success',
                primary_remote_id='fixture-'+str(i),visibility_state='public',confirmation_kind='fake_receipt') for i in range(2)])
            worker=SocialWorker(repo,adapters={('facebook','fake'):fake})
            try:
                claims=await worker.db(repo.claim_due,2)
                assert len(claims)==2
                await asyncio.gather(*(worker.process(claim) for claim in claims))
                assert fake.calls==2 and peak==2
            finally:
                await worker.close()
            return peak
        with probe.capture():
            external_peak=asyncio.run(two_slots())
        result['two_concurrent_fake_publications']={**probe.summary(),
                                                    'peak_fake_external_operations':external_peak}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url',required=True)
    args=parser.parse_args()
    try:
        url=local_url(args.database_url)
        # This process-only import configuration does not touch any .env file,
        # running application, ingestion schedule or deployed configuration.
        dsn=url.render_as_string(hide_password=False)
        os.environ['DATABASE_URL']=dsn
        os.environ['PYTHON_DOTENV_DISABLED']='1'
        report={'measurement':'UTF-8 decoded selected-value estimate; excludes protocol/TLS/pooler bytes',
                'fixture':{'jobs':100,'matched_jobs':80,'writer_records':20,'distinct_sources':2,
                           'diagnostic_bytes_per_job':65536,'metadata_bytes_per_source':65536},
                # Revalidate original caller input at each fixture boundary;
                # generated hostaddr is an engine option, not a caller option.
                'ingestion_stats':measure_stats(args.database_url),
                'source_documents':measure_writers(args.database_url),
                'social_worker':measure_worker(args.database_url)}
    except Exception as error:
        print(json.dumps({'outcome':'benchmark_failed','error_type':type(error).__name__}),file=sys.stderr)
        return 1
    print(json.dumps(report,sort_keys=True,indent=2))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
