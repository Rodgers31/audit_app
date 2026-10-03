"""Execute the existing source-publisher golden cases on isolated PostgreSQL."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from harness import seed_country
from models import Country


@pytest.mark.parametrize('name',[
    'test_world_bank_rows_are_filed_under_the_world_bank',
    'test_misfiled_production_documents_are_corrected_in_place',
    'test_undeclared_fixture_rows_keep_the_kra_default',
    'test_undeclared_row_never_overwrites_a_declared_publisher',
])
def test_existing_provenance_golden(pg_fixture,name):
    engine,_=pg_fixture
    country_id,_=seed_country(engine)
    path=Path(__file__).resolve().parents[1]/'test_revenue_source_publisher.py'
    spec=importlib.util.spec_from_file_location('egress_existing_revenue_golden',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with Session(engine) as db:
        getattr(module,name)(db_session=db,seed_country=db.get(Country,country_id))
