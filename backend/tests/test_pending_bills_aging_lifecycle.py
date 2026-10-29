"""Aging selection survives only a qualified reread of the identical stock.

The acquisition bytes are synthetic. Real retained source execution is a
separate, explicitly supplied offline qualification, never a live adoption.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from models import Country, Extraction, SourceDocument
from seeding.domains.pending_bills import aging
from services.pending_bills_aging import aging_observations
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties
from test_pending_bills_assembly_aging import source_pair, write_pair


def test_identical_stock_only_refresh_keeps_both_qualified_cohort_pointers(
    pg_engine, tmp_path, monkeypatch,
):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        original = deepcopy(db.query(SourceDocument).one().meta)
        count = db.query(Extraction).count()
        write_pair(db, records, None, None)
        db.commit()
    with Session(pg_engine) as db:
        result = aging_observations(db, as_at=aging.AS_AT)
        for scope in ('county_executive', 'county_assembly'):
            key = aging.scope_contract(scope)['metadata_key']
            assert result[scope]['status'] == 'qualified', 'Unchanged stock lost its qualified aging cohort'
            assert db.query(SourceDocument).one().meta[key] == original[key]
        assert db.query(Extraction).count() == count
        assert result['county_assembly']['reported_total'] == 6321350000
        assert result['combined']['status'] == result['national']['status'] == 'unavailable'


@pytest.mark.parametrize('change', ['amount', 'artifact', 'missing_evidence', 'serialized_evidence',
                                   'title', 'url', 'absence', 'receipt', 'cohort'])
def test_stock_replacement_or_missing_authority_clears_pointers(
    pg_engine, tmp_path, monkeypatch, change,
):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        original_count = db.query(Extraction).filter(Extraction.extractor.in_(
            ['pending-bills-aging-v1', 'pending-bills-assembly-aging-v2'])).count()
        kwargs = {}
        records = deepcopy(records)
        if change in ('title', 'url'):
            replacement = tmp_path / 'replacement'
            replacement.mkdir()
            records, _, _ = source_pair(replacement, monkeypatch)
        if change == 'amount':
            records[0] = replace(records[0], total_pending=Decimal(123))
        elif change == 'artifact':
            for record in records:
                record.source_evidence[0]['_response_receipt']['digest'] = 'b' * 64
        elif change == 'missing_evidence':
            records[-1].source_evidence = []
        elif change == 'serialized_evidence':
            for record in records:
                record.source_evidence = [dict(e) for e in record.source_evidence]
        elif change == 'title':
            kwargs['source_title'] = 'Another source edition'
        elif change == 'url':
            kwargs['source_url'] = 'https://cob.go.ke/reissued.pdf'
        elif change == 'absence':
            kwargs['county_table'] = {'as_at': aging.AS_AT, 'table': 'Table 2.10', 'withheld': ['Nandi']}
        elif change == 'receipt':
            extraction = db.query(Extraction).filter(Extraction.extractor == 'pdf-receipt-v1').first()
            extraction.extracted_json = {'response_receipt': {}}
        elif change == 'cohort':
            extraction = db.query(Extraction).filter(Extraction.extractor == 'pending-bills-assembly-aging-v2').one()
            broken = deepcopy(extraction.extracted_json)
            broken['version'] = 999
            extraction.extracted_json = broken
        write_pair(db, records, None, None, **kwargs)
        db.commit()
        result = aging_observations(db, as_at=aging.AS_AT)
        assert result['county_assembly']['status'] == 'unavailable'
        if change != 'cohort':
            assert result['county_executive']['status'] == 'unavailable'
        assert db.query(Extraction).filter(Extraction.extractor.in_(
            ['pending-bills-aging-v1', 'pending-bills-assembly-aging-v2'])).count() == original_count


def test_stock_only_rollback_keeps_original_selection(pg_engine, tmp_path, monkeypatch):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        write_pair(db, records, None, None)
        db.rollback()
    with Session(pg_engine) as db:
        assert aging_observations(db, as_at=aging.AS_AT)['county_assembly']['status'] == 'qualified'


def test_adopted_stock_is_freshly_parsed_without_acquiring_new_aging(
    pg_engine, tmp_path, monkeypatch,
):
    from types import SimpleNamespace
    import httpx
    from seeding import cob_cbirr, pdf_parsers
    from seeding.config import SeedingSettings
    from seeding.domains.pending_bills import fetcher
    from test_pending_bills_assembly_aging import entries
    from test_pending_bills_aging_persistence import URL

    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    monkeypatch.delenv('SEED_PENDING_BILLS_AGING_ENABLED', raising=False)
    monkeypatch.delenv('SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED', raising=False)
    monkeypatch.setattr(fetcher, 'year_end_cbirr_links', lambda _: [URL])
    monkeypatch.setattr(cob_cbirr, 'download_cbirr', lambda *a: SimpleNamespace(path=tmp_path / 'input.pdf'))
    calls = []
    class Parser:
        def __init__(self, path): pass
        def parse(self):
            calls.append(True)
            return [dict(e, fiscal_year='FY2025/26') for e in entries()]
    class Client:
        def get(self, url, **kw):
            return httpx.Response(200, content=b'listing', request=httpx.Request('GET', url))
    monkeypatch.setattr(pdf_parsers, 'CbirrYearEndPayablesParser', Parser)
    monkeypatch.setattr(aging, '_parse_pdf_scopes', lambda *a: pytest.fail('Unselected aging acquisition'))
    settings = SeedingSettings(_env_file=None, cache_path=tmp_path / 'cache',
                               storage_path=tmp_path, parse_cache_enabled=True)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        for _ in range(2):
            payload = fetcher.fetch_county_payables_payload(Client(), settings, session=db)
            assert 'aging' not in payload and 'assembly_aging' not in payload
        assert len(calls) == 2, 'Cached JSON cannot qualify the current stock behind an adopted cohort'
