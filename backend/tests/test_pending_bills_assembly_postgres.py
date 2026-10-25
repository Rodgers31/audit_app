"""Owned actual PostgreSQL controls; genuine cells with synthetic acquisition."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy.orm import Session
from models import Country,Loan,Extraction,SourceDocument
from seeding.domains.pending_bills import aging
from services.pending_bills_aging import aging_observations,ASSEMBLY_EXTRACTOR
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties
from test_pending_bills_assembly_aging import source_pair,write_pair,SCOPE
import pytest


def test_pg_pair_commit_reopen_replay_rollback_and_current_authority(pg_engine,tmp_path,monkeypatch):
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db,db.query(Country).one().id)
        write_pair(db,records,executive,assembly);db.commit()
    with Session(pg_engine) as db:
        assert aging_observations(db,as_at=aging.AS_AT)[SCOPE]['reported_total']==6321350000
        before_cohorts=db.query(Extraction).filter(Extraction.extractor.in_(['pending-bills-aging-v1',ASSEMBLY_EXTRACTOR])).count()
        write_pair(db,records,executive,assembly);db.commit()
        assert db.query(Extraction).filter(Extraction.extractor.in_(['pending-bills-aging-v1',ASSEMBLY_EXTRACTOR])).count()==before_cohorts==2
        # Existing receipt adapter retains acquisitions per Session; receipts
        # may append across reopen, while the actual cohort stays deduplicated.
        before=db.query(Extraction).count()
        # Both tables roll back if the second persistence operation fails late.
        import seeding.domains.pending_bills.aging as module
        original=module.persist_aging
        def fail(session,source,cohort,**kw):
            if cohort['scope']==SCOPE: raise RuntimeError('inert late assembly failure')
            return original(session,source,cohort,**kw)
        rollback_path=tmp_path/'rollback';rollback_path.mkdir()
        rollback_records,rollback_exec,rollback_assembly=source_pair(rollback_path,monkeypatch)
        with monkeypatch.context() as patch:
            patch.setattr(module,'persist_aging',fail)
            with pytest.raises(RuntimeError,match='late assembly'):
                write_pair(db,rollback_records,rollback_exec,rollback_assembly,source_title='B86 rollback title')
        db.commit()
    with Session(pg_engine) as db:
        assert db.query(SourceDocument).count()==1
        assert db.query(Extraction).count()==before
        row=db.query(Loan).first();row.provenance={**row.provenance,'publication_batch':'b'*64};db.flush()
        result=aging_observations(db,as_at=aging.AS_AT)
        assert result[SCOPE]['status']==result['county_executive']['status']=='unavailable'
        db.rollback()
        assert aging_observations(db,as_at=aging.AS_AT)[SCOPE]['status']=='qualified'
        context={(r.source_document_id,r.provenance['publication_batch']) for r in db.query(Loan).all()}
        new=tmp_path/'replacement';new.mkdir()
        new_records,new_exec,new_assembly=source_pair(new,monkeypatch)
        with Session(pg_engine) as writer:
            write_pair(writer,new_records,new_exec,new_assembly,source_title='B86 replacement title');writer.commit()
        assert aging_observations(db,as_at=aging.AS_AT,stock_context=context)[SCOPE]['status']=='unavailable'
        assert aging_observations(db,as_at=aging.AS_AT)[SCOPE]['status']=='qualified'
        assert db.query(Extraction).filter(Extraction.extractor==ASSEMBLY_EXTRACTOR).count()==2
        assert db.query(SourceDocument).count()==2
        # An unaged replacement title must not revive either old pointer.
        newer=tmp_path/'unaged';newer.mkdir()
        r,e,a=source_pair(newer,monkeypatch)
        write_pair(db,r,None,None,source_title='B86 unaged replacement');db.commit()
    with Session(pg_engine) as db:
        result=aging_observations(db,as_at=aging.AS_AT)
        assert result[SCOPE]['status']==result['county_executive']['status']=='unavailable'
        assert db.query(Extraction).filter(Extraction.extractor==ASSEMBLY_EXTRACTOR).count()==2


def test_pg_concurrent_pair_writers(pg_engine,tmp_path,monkeypatch):
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db,db.query(Country).one().id);db.commit()
    barrier=Barrier(2)
    def worker():
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            result=write_pair(db,records,executive,assembly);db.commit();return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker) for _ in range(2)]
        assert sorted(f.result(timeout=60) for f in futures)==[(0,46),(46,0)]
    with Session(pg_engine) as db:
        assert db.query(SourceDocument).count()==1
        assert db.query(Extraction).filter(Extraction.extractor==ASSEMBLY_EXTRACTOR).count()==1
        assert aging_observations(db,as_at=aging.AS_AT)[SCOPE]['reported_total']==6321350000


def test_pg_actual_http_summary_and_missing_band_county(pg_engine,tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    import main
    from database import get_db
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db,db.query(Country).one().id)
        write_pair(db,records,executive,assembly);db.commit()
    def get_owned_db():
        with Session(pg_engine) as db: yield db
    main.app.dependency_overrides[get_db]=get_owned_db
    try:
        with TestClient(main.app) as client:
            response=client.get('/api/v1/pending-bills/summary')
            assert response.status_code==200
            assert response.json()['aging_observations'][SCOPE]['reported_total']==6321350000
            county=client.get('/api/v1/pending-bills/counties/narok')
            assert county.status_code==200
            assert [b['amount'] for b in county.json()['aging_observations'][SCOPE]['buckets']]==[None]*4
    finally:
        main.app.dependency_overrides.pop(get_db,None)


def test_pg_altered_assembly_storage_must_rollback(pg_engine,tmp_path,monkeypatch):
    from sqlalchemy import text
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db,db.query(Country).one().id);db.commit()
        db.execute(text("""CREATE FUNCTION b86_alter_assembly() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.extractor = 'pending-bills-assembly-aging-v2' THEN
            NEW.extracted_json := jsonb_set(NEW.extracted_json, '{version}', '999'::jsonb);
          END IF;
          RETURN NEW;
        END $$"""))
        db.execute(text('CREATE TRIGGER b86_alter_assembly BEFORE INSERT ON extractions FOR EACH ROW EXECUTE FUNCTION b86_alter_assembly()'))
        db.commit()
        with pytest.raises(ValueError,match='Aging|aging|persist'):
            write_pair(db,records,None,assembly)
        db.commit()
    with Session(pg_engine) as db:
        assert db.query(Loan).count()==db.query(SourceDocument).count()==db.query(Extraction).count()==0
