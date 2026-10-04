"""Source resolution reads each identity once and retains mutation semantics."""
from dataclasses import replace
from decimal import Decimal
import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session

from models import (BudgetLine, DocumentStatus, DocumentType, RevenueBySource, SourceDocument)
from seeding.config import SeedingSettings
from seeding.domains.national_budget.writer import persist_national_budget_records
from seeding.domains.revenue_by_source.writer import persist_revenue_records
from seeding.types import DomainRunContext
from harness import budget_records, revenue_records, seed_country


WRITERS = [('budget',persist_national_budget_records,budget_records),
           ('revenue',persist_revenue_records,revenue_records)]


def source_rows(engine,records,country_id):
    with Session(engine) as db:
        for url in {r.source_url for r in records}:
            db.add(SourceDocument(country_id=country_id,publisher='Old publisher',title='Old title',
                url=url,doc_type=DocumentType.REPORT,status=DocumentStatus.FAILED,
                fetch_date=datetime(2020,1,1,tzinfo=timezone.utc),
                last_seen_at=datetime(2020,1,1,tzinfo=timezone.utc),
                meta={'untouched':'PRIVATE_METADATA_'+('x'*65536)}))
        db.commit()


@pytest.mark.parametrize('kind,writer,records_fn',WRITERS)
@pytest.mark.parametrize('existing',[False,True])
def test_source_reads_are_bounded_by_distinct_urls_and_exclude_unused_payload(pg_fixture,kind,writer,records_fn,existing):
    engine,probe = pg_fixture
    country_id,_ = seed_country(engine)
    records=records_fn()
    if existing:
        source_rows(engine,records,country_id)
    with Session(engine) as db:
        with probe.capture():
            stats=writer(db,iter(records),SeedingSettings(),DomainRunContext(since=None,dry_run=False))
            db.flush()
        assert stats.errors==[] and stats.created==len(records)
        db.commit()
    samples=probe.selected('source_documents')
    assert len(samples)==2
    assert sum(s.rows for s in samples)==(2 if existing else 0)
    assert sum(s.selected_value_bytes for s in samples)<1024
    assert not any('metadata' in s.columns or 'file_path' in s.columns for s in samples)
    with Session(engine) as db:
        sources=list(db.scalars(select(SourceDocument)))
        assert len(sources)==2
        if existing:
            assert all('PRIVATE_METADATA_' in s.meta['untouched'] for s in sources)
        if kind=='revenue':
            assert all(s.publisher=='Declared publisher' for s in sources)
            assert db.query(RevenueBySource).count()==len(records)
        else:
            assert all(s.status==DocumentStatus.AVAILABLE for s in sources)
            assert db.query(BudgetLine).count()==len(records)


@pytest.mark.parametrize('kind,writer,records_fn',WRITERS)
def test_rollback_discards_new_sources_and_next_call_queries_again(pg_fixture,kind,writer,records_fn):
    engine,probe=pg_fixture
    seed_country(engine)
    records=records_fn()
    with Session(engine) as db:
        stats=writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=True))
        assert stats.created==len(records) and not stats.errors
        db.flush()
        db.rollback()
        assert db.query(SourceDocument).count()==0
        with probe.capture():
            stats=writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        assert len(probe.selected('source_documents'))==2
        assert stats.created==len(records) and not stats.errors
        db.commit()


def test_revenue_declarations_remain_ordered_and_undeclared_rows_preserve_labels(pg_fixture):
    engine,_=pg_fixture
    seed_country(engine)
    base=revenue_records(1)[0]
    records=[base,replace(base,revenue_type='Type B',publisher=None,source_title=None),
             replace(base,revenue_type='Type C',publisher='Later publisher',source_title='Later title'),
             replace(base,revenue_type='Type D',publisher=None,source_title=None)]
    with Session(engine) as db:
        stats=persist_revenue_records(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        assert stats.created==4 and not stats.errors
        source=db.scalar(select(SourceDocument))
        assert (source.publisher,source.title)==('Later publisher','Later title')
        assert all(row.meta==base.metadata for row in db.scalars(select(RevenueBySource)))
        db.commit()
    # A fresh invocation observes changes from another session, not a global cache.
    with engine.begin() as conn:
        conn.execute(text("UPDATE source_documents SET publisher='External publisher',title='External title'"))
    with Session(engine) as db:
        persist_revenue_records(db,[records[-1]],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        source=db.scalar(select(SourceDocument))
        assert (source.publisher,source.title)==('External publisher','External title')


@pytest.mark.parametrize('kind,writer,records_fn',WRITERS)
def test_source_selected_byte_estimate_excludes_existing_large_metadata(pg_fixture,kind,writer,records_fn):
    engine,probe=pg_fixture
    country_id,_=seed_country(engine)
    records=records_fn(2)
    source_rows(engine,records,country_id)
    with Session(engine) as db,probe.capture():
        writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
    assert sum(s.selected_value_bytes for s in probe.selected('source_documents'))<1024


@pytest.mark.parametrize('kind,writer,records_fn',WRITERS)
def test_existing_source_mutations_roll_back_after_actual_flush_failure(pg_fixture,kind,writer,records_fn):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    records=records_fn(2)
    source_rows(engine,records,country_id)
    def fail_write(conn,cursor,statement,parameters,context,executemany):
        table='budget_lines' if kind=='budget' else 'revenue_by_source'
        if statement.startswith('INSERT INTO '+table):
            raise RuntimeError('Injected local write failure')
    with Session(engine) as db:
        event.listen(engine,'before_cursor_execute',fail_write)
        try:
            if kind=='budget':
                with pytest.raises(RuntimeError,match='Injected local write failure'):
                    writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
                    db.flush()
            else:
                stats=writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
                assert stats.errors
        finally:
            event.remove(engine,'before_cursor_execute',fail_write)
            db.rollback()
    with Session(engine) as db:
        sources=list(db.scalars(select(SourceDocument)))
        assert all(s.publisher=='Old publisher' and s.title=='Old title' and
                   s.status==DocumentStatus.FAILED and s.last_seen_at.year==2020 for s in sources)
        assert all('PRIVATE_METADATA_' in s.meta['untouched'] for s in sources)
        assert db.query(BudgetLine).count()==0 and db.query(RevenueBySource).count()==0


def test_revenue_absence_and_publication_provenance_semantics_are_retained(pg_fixture):
    engine,_=pg_fixture
    seed_country(engine)
    record=revenue_records(1)[0]
    with Session(engine) as db:
        stats=persist_revenue_records(db,[record],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        assert not stats.errors
        row=db.scalar(select(RevenueBySource))
        row.publishable=True
        row.quarantine_reason='existing-review-marker'
        row.source_hash='reviewed-hash'
        row.page_ref='p.17'
        db.commit()
    with Session(engine) as db:
        unavailable=replace(record,amount_billion_kes=None,metadata={'basis':'projected'})
        stats=persist_revenue_records(db,[unavailable],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        row=db.scalar(select(RevenueBySource))
        assert stats.skipped==1 and row.amount_billion_kes==Decimal(0)
        assert row.meta==record.metadata
        withdrawn=replace(unavailable,metadata={'absent_reason':'withdrawn by source'})
        stats=persist_revenue_records(db,[withdrawn],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        assert stats.updated==1 and row.amount_billion_kes is None
        assert row.meta==withdrawn.metadata
        assert row.publishable and row.quarantine_reason=='existing-review-marker'
        assert (row.source_hash,row.page_ref)==('reviewed-hash','p.17')


def test_national_measure_replacement_keeps_declared_rows_and_other_periods(pg_fixture):
    engine,_=pg_fixture
    seed_country(engine)
    record=budget_records(1)[0]
    with Session(engine) as db:
        proxy=replace(record,subcategory='Proxy',provenance_extra={'measure':'exchequer_issues'})
        older=replace(proxy,period_label='FY2024/25')
        persist_national_budget_records(db,[proxy,older],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        db.commit()
    with Session(engine) as db:
        stats=persist_national_budget_records(db,[record],SeedingSettings(),DomainRunContext(since=None,dry_run=False,job_id=17))
        db.commit()
        assert stats.superseded==1
        rows=list(db.scalars(select(BudgetLine)))
        assert len(rows)==2
        current=next(row for row in rows if row.subcategory==record.subcategory)
        assert current.actual_spent==record.actual_spent and current.allocated_amount==record.allocated_amount
        assert current.page_ref==record.page_ref and not current.publishable
        assert current.provenance[-1]=={'source':record.source,'data_quality':'official',
            'ingestion_job_id':17,'measure':'expenditure','period':'annual'}
        assert next(row for row in rows if row.subcategory=='Proxy').provenance[-1]['measure']=='exchequer_issues'


def test_relabel_logs_are_bounded_and_exclude_declared_content(pg_fixture,caplog):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    record=replace(revenue_records(1)[0],publisher='PRIVATE_PUBLISHER',source_title='PRIVATE_TITLE')
    source_rows(engine,[record],country_id)
    with Session(engine) as db,caplog.at_level(logging.INFO):
        stats=persist_revenue_records(db,[record],SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        assert not stats.errors
    assert not any(secret in caplog.text for secret in ('PRIVATE_PUBLISHER','PRIVATE_TITLE','PRIVATE_METADATA_','fixture.invalid'))
    assert 'source_document_relabelled' in caplog.text and 'revenue_persistence_prepared' in caplog.text


def test_failure_log_excludes_exception_content_while_returned_error_contract_is_preserved(pg_fixture,caplog,monkeypatch):
    from seeding.domains.revenue_by_source import writer
    engine,_=pg_fixture
    seed_country(engine)
    with Session(engine) as db:
        initial=writer.persist_revenue_records(db,revenue_records(1),SeedingSettings(),
                                             DomainRunContext(since=None,dry_run=False))
        assert not initial.errors
        db.commit()
    def fail_updates(*args):
        raise RuntimeError('PRIVATE_PROVIDER_BODY https://fixture.invalid?credential=PRIVATE_TOKEN')
    monkeypatch.setattr(writer,'_apply_updates',fail_updates)
    with Session(engine) as db,caplog.at_level(logging.WARNING):
        stats=writer.persist_revenue_records(db,revenue_records(1),SeedingSettings(),
                                           DomainRunContext(since=None,dry_run=False))
        assert len(stats.errors)==1 and 'PRIVATE_PROVIDER_BODY' in stats.errors[0]
        db.rollback()
    assert 'revenue_record_persistence_failed' in caplog.text
    assert not any(secret in caplog.text for secret in ('PRIVATE_PROVIDER_BODY','fixture.invalid','PRIVATE_TOKEN'))
    entry=next(entry for entry in caplog.records if entry.message=='revenue_record_persistence_failed')
    assert entry.error_type=='RuntimeError'


@pytest.mark.parametrize('kind,writer,records_fn',WRITERS)
def test_ambiguous_duplicate_source_urls_never_choose_arbitrary_provenance(pg_fixture,kind,writer,records_fn):
    from sqlalchemy.exc import MultipleResultsFound
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    records=records_fn(1)
    source_rows(engine,records,country_id)
    source_rows(engine,records,country_id)
    with Session(engine) as db:
        if kind=='budget':
            with pytest.raises(MultipleResultsFound):
                writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
        else:
            stats=writer(db,records,SeedingSettings(),DomainRunContext(since=None,dry_run=False))
            assert stats.errors and stats.created==0
        assert db.query(BudgetLine).count()==0 and db.query(RevenueBySource).count()==0
