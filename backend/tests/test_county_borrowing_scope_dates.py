"""Source scope review dates are neither publication nor stock dates."""
from copy import deepcopy
import pytest
from sqlalchemy import select

from county_borrowing_fixture import borrowing_pg, owned  # noqa: F401
from test_county_borrowing_producer import specimen, persist  # noqa: F401
from seeding import county_borrowing_contract as contract
from services.county_borrowing_coverage import county_borrowing_coverage
from models import Entity


def test_review_date_survives_writer_pg_reader_without_becoming_stock(borrowing_pg, specimen):
    from services.county_debt import county_debt_rows
    from services.financial_publication import county_debt_summary
    spec, _, _ = specimen
    spec['scope_reviewed_on'] = '2026-10-25'
    spec['instruments'] = []
    spec['status'] = 'not_reported_in_checked_source'
    _, factory = borrowing_pg
    with owned(factory) as context:
        persist(factory, context, specimen)
    with factory() as db:
        entity = db.scalar(select(Entity).where(Entity.slug == 'kisii-county'))
        coverage = county_borrowing_coverage(db, [entity.id])[entity.id]
        account = coverage['sources'][0]
        assert account['scope_reviewed_on'] == '2026-10-25'
        assert account['reporting_period_end'] == '2025-06-30'
        assert 'publication_date' not in account
        result = county_debt_summary(county_debt_rows(db, [entity.id]), source_coverage=coverage)
        assert result['total_debt'] is None
        assert result['debt_as_at'] is None
        assert result['debt_source_coverage'] == coverage


@pytest.mark.parametrize('value', [True, 20261025, '', '2026-1-25', '2026-02-30',
                                    '2026-10', '2026-10-25T00:00:00Z', '9999-12-31', None])
def test_malformed_scope_review_date_refuses_projection(db_session, seed_entity, monkeypatch, value):
    from test_county_borrowing_review import retained_coverage
    key = 'treasury_guaranteed_stock_2025'
    retained_coverage(db_session, seed_entity.country_id, key)
    spec = deepcopy(contract.EDITIONS[key])
    spec['scope_reviewed_on'] = value
    monkeypatch.setitem(contract.EDITIONS, key, spec)
    with pytest.raises(RuntimeError, match='scope review date'):
        county_borrowing_coverage(db_session, [seed_entity.id])


def test_unknown_review_date_remains_explicitly_unknown(borrowing_pg, specimen):
    _, factory = borrowing_pg
    specimen[0].pop('scope_reviewed_on', None)
    with owned(factory) as context:
        persist(factory, context, specimen)
    with factory() as db:
        entity = db.scalar(select(Entity).where(Entity.slug == 'kisii-county'))
        account = county_borrowing_coverage(db, [entity.id])[entity.id]['sources'][0]
        assert account['scope_reviewed_on'] is None


@pytest.mark.parametrize('path', ['/api/v1/counties', '/api/v1/counties/code:047',
                                 '/api/v1/counties/code:047/comprehensive', '/api/v1/counties/code:047/debt'])
def test_scope_dates_reach_all_existing_http_adapters(client, db_session, seed_entity, path):
    import main
    from test_county_borrowing_review import retained_coverage, response_debt
    seed_entity.canonical_name = 'Nairobi County'
    retained_coverage(db_session, seed_entity.country_id)
    db_session.commit()
    main.clear_all_caches()
    response = client.get(path)
    assert response.status_code == 200, response.text[:500]
    result = response_debt(path, response.json())
    assert result['total_debt'] is None
    assert result['debt_as_at'] is None
    assert result['debt_source_coverage']['sources'][0]['scope_reviewed_on'] == '2026-10-25'
    assert result['debt_source_coverage']['sources'][0]['reporting_period_end'] == '2025-06-30'


def test_review_annotations_do_not_rewrite_existing_extraction_or_parser_identity(monkeypatch):
    key = 'treasury_guaranteed_stock_2025'
    before = contract.expected_extraction(key)
    spec = deepcopy(contract.EDITIONS[key])
    spec['scope_reviewed_on'] = '2026-10-25'
    monkeypatch.setitem(contract.EDITIONS, key, spec)
    assert contract.expected_extraction(key) == before
    assert before['instruments'] == []
