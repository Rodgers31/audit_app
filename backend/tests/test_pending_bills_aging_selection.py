"""Independent executable controls over candidate writer and actual PostgreSQL."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session
from models import Country, DocumentStatus, SourceDocument
from seeding.domains.pending_bills import aging
from services.pending_bills_aging import aging_observations
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties
from test_pending_bills_assembly_aging import source_pair, write_pair


def test_same_day_source_replacement_does_not_revive_historical_pointer(pg_engine, tmp_path, monkeypatch):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        original_source = db.query(SourceDocument).one().id
        assert aging_observations(db, as_at=aging.AS_AT)['county_assembly']['status'] == 'qualified'
        replacement = tmp_path / 'replacement'; replacement.mkdir()
        new_records, _, _ = source_pair(replacement, monkeypatch)
        new_records[0] = replace(new_records[0], total_pending=Decimal(12000000))
        write_pair(db, new_records, None, None, source_title='Replacement same-day stock')
        db.commit()
        assert db.query(SourceDocument).count() == 2
        assert aging_observations(db, as_at=aging.AS_AT)['county_assembly']['status'] == 'unavailable'
        # This is an ordinary writer retry against the old source, no supplied
        # new aging observations. History may remain, but cannot revive itself.
        write_pair(db, records, None, None)
        db.commit()
        result = aging_observations(db, as_at=aging.AS_AT)
        assert result['county_assembly']['status'] == 'unavailable', {
            'source_a':original_source,'selected_source':result['county_assembly'].get('source_document_id'),
            'failure':'Historical source A pointer revived after source-B stock replacement'}


@pytest.mark.parametrize('invalid_source', ['failed', 'md5', 'artifact'])
def test_current_source_invalidation_does_not_keep_an_old_pointer(pg_engine, tmp_path, monkeypatch, invalid_source):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly)
        db.commit()
        source = db.query(SourceDocument).one()
        if invalid_source == 'failed': source.status = DocumentStatus.FAILED
        elif invalid_source == 'md5': source.md5 = 'b' * 32
        else: source.meta = {**source.meta, 'pdf_artifact_v1':{'sha256':'b' * 64,'md5':'b' * 32}}
        db.commit()
        assert aging_observations(db, as_at=aging.AS_AT)['county_assembly']['status'] == 'unavailable'
        write_pair(db, records, None, None)
        db.commit()
        result = aging_observations(db, as_at=aging.AS_AT)
        assert result['county_assembly']['status'] == 'unavailable', {
            'failure':'Invalidated current source retained qualified aging','variant':invalid_source}
