"""Independent Spec controls; synthetic acquisition, actual PG writer/reader."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from threading import Barrier
import pytest
from sqlalchemy.orm import Session
from models import Country, Extraction, SourceDocument
from seeding.domains.pending_bills import aging, fetcher
from services.pending_bills_aging import aging_observations
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties, URL
from test_pending_bills_assembly_aging import source_pair, write_pair


def setup(db, path, monkeypatch, *, executive=True):
    records, ex, assembly = source_pair(path, monkeypatch)
    populate_counties(db, db.query(Country).one().id)
    write_pair(db, records, ex if executive else None, assembly)
    db.commit()
    return records


def test_assembly_only_survives_unaged_refresh_without_executive_substitution(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        records = setup(db,tmp_path,monkeypatch,executive=False)
        write_pair(db,records,None,None);db.commit()
    with Session(pg_engine) as db:
        output=aging_observations(db,as_at=aging.AS_AT,county='Narok County')
        assert output['county_assembly']['status']=='qualified'
        assert output['county_executive']['status']=='unavailable'
        assert [bucket['amount'] for bucket in output['county_assembly']['buckets']]==[None]*4
        assert output['county_assembly']['reported_total']==17920000
        assert output['national']['status']==output['combined']['status']=='unavailable'


@pytest.mark.parametrize('bad_id',[True,None,'1',{},-1])
def test_malformed_selected_extraction_is_not_promoted(pg_engine,tmp_path,monkeypatch,bad_id):
    with Session(pg_engine) as db:
        records=setup(db,tmp_path,monkeypatch)
        source=db.query(SourceDocument).one();meta=deepcopy(source.meta)
        meta['pending_bills_assembly_aging_v2']['extraction_id']=bad_id
        source.meta=meta;db.commit()
        write_pair(db,records,None,None);db.commit()
        result=aging_observations(db,as_at=aging.AS_AT)
        assert result['county_assembly']['status']=='unavailable'
        assert result['county_executive']['status']=='qualified'


def test_changed_fiscal_year_does_not_select_old_aging(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        records=setup(db,tmp_path,monkeypatch)
        mismatched=[replace(r,fiscal_year='FY2024/25') for r in records]
        write_pair(db,mismatched,None,None);db.commit()
        result=aging_observations(db,as_at=aging.AS_AT)
        assert result['county_assembly']['status']==result['county_executive']['status']=='unavailable'


def test_empty_write_is_not_a_stock_replacement(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        setup(db,tmp_path,monkeypatch)
        assert write_pair(db,[],None,None)==(0,0)
        db.commit()
        assert aging_observations(db,as_at=aging.AS_AT)['county_assembly']['status']=='qualified'


def test_concurrent_ordinary_stock_writers_keep_one_cohort(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        records=setup(db,tmp_path,monkeypatch)
    barrier=Barrier(2)
    def worker():
        with Session(pg_engine) as db:
            barrier.wait(timeout=10)
            result=write_pair(db,records,None,None);db.commit();return result
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(worker) for _ in range(2)]
        assert [f.result(timeout=45) for f in futures]==[(0,46),(0,46)]
    with Session(pg_engine) as db:
        assert aging_observations(db,as_at=aging.AS_AT)['county_assembly']['status']=='qualified'
        assert db.query(Extraction).filter(Extraction.extractor=='pending-bills-assembly-aging-v2').count()==1


def test_historical_source_does_not_force_unselected_heavy_parser(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        setup(db,tmp_path,monkeypatch)
        path=tmp_path/'replacement';path.mkdir()
        replacement,_,_=source_pair(path,monkeypatch)
        write_pair(db,replacement,None,None,source_title='Changed annual edition title');db.commit()
        assert aging_observations(db,as_at=aging.AS_AT)['county_assembly']['status']=='unavailable'
        assert fetcher._has_aging_pointer(db,URL) is False, 'Historical pointer forced heavy stock parsing with both aging flags off'


def test_replaced_source_return_does_not_resurrect_old_pointer(pg_engine,tmp_path,monkeypatch):
    with Session(pg_engine) as db:
        setup(db,tmp_path,monkeypatch)
        path_b=tmp_path/'edition_b';path_b.mkdir()
        records_b,_,_=source_pair(path_b,monkeypatch)
        write_pair(db,records_b,None,None,source_title='Replacement title');db.commit()
        assert aging_observations(db,as_at=aging.AS_AT)['county_assembly']['status']=='unavailable'
        path_a=tmp_path/'edition_a_return';path_a.mkdir()
        records_a,_,_=source_pair(path_a,monkeypatch)
        write_pair(db,records_a,None,None);db.commit()
        assert aging_observations(db,as_at=aging.AS_AT)['county_assembly']['status']=='unavailable', 'History A -> B -> A revived old aging without acquiring a new cohort'
