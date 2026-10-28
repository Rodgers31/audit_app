"""Stale ORM identity-map state must not revive explicitly invalidated history."""
from copy import deepcopy
from sqlalchemy.orm import Session
from models import Country, SourceDocument
from seeding.domains.pending_bills import aging
from services.pending_bills_aging import aging_observations
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties
from test_pending_bills_assembly_aging import source_pair, write_pair


def test_stale_source_identity_map_cannot_revive_invalidated_pointer(pg_engine, tmp_path, monkeypatch):
    records, executive, assembly = source_pair(tmp_path, monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db, db.query(Country).one().id)
        write_pair(db, records, executive, assembly); db.commit()
    with Session(pg_engine) as stale:
        source = stale.query(SourceDocument).one()
        assert source.meta['pending_bills_assembly_aging_v2'] is not None
        # A separately committed unqualified stock reread explicitly clears
        # selection even when its values, source and batch have not changed.
        with Session(pg_engine) as writer:
            incoming = deepcopy(records)
            for record in incoming: record.source_evidence = []
            write_pair(writer, incoming, None, None); writer.commit()
        # Retain the stale identity in this transaction. A query alone does
        # not refresh its meta, even at READ COMMITTED isolation.
        assert source.meta['pending_bills_assembly_aging_v2'] is not None
        write_pair(stale, records, None, None); stale.commit()
    with Session(pg_engine) as reader:
        assert aging_observations(reader, as_at=aging.AS_AT)['county_assembly']['status'] == 'unavailable', 'Stale identity map revived explicitly invalidated cohort history'
