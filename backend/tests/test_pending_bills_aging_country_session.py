"""A strong Country reference makes the stale writer identity explicit."""
from sqlalchemy.orm import Session
from models import Country, SourceDocument
from seeding.domains.pending_bills import aging
from test_pending_bills_aging_postgres import pg_engine
from test_pending_bills_aging_persistence import populate_counties
from test_pending_bills_assembly_aging import source_pair, write_pair


def test_writer_refuses_a_strongly_held_stale_country_identity(pg_engine,tmp_path,monkeypatch):
    records,executive,assembly=source_pair(tmp_path,monkeypatch)
    with Session(pg_engine) as db:
        populate_counties(db,db.query(Country).one().id)
        write_pair(db,records,executive,assembly);db.commit()
    with Session(pg_engine) as stale:
        source=stale.query(SourceDocument).one()
        country=source.country
        assert country.iso_code=='KEN'
        with Session(pg_engine) as writer:
            writer.get(Country,source.country_id).iso_code='TZA';writer.commit()
        assert country.iso_code=='KEN'
        write_pair(stale,records,None,None);stale.commit()
    with Session(pg_engine) as reader:
        assert reader.query(SourceDocument).one().meta['pending_bills_assembly_aging_v2'] is None, 'Strongly held stale Country licensed retention'
