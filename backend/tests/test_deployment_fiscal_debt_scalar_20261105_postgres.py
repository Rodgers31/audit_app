"""Actual-PG scalar reader controls: retain cited history, hold failed evidence.

The owning runner must supply the existing isolated PostgreSQL fixture plugin.
Inert HTTP/decoder fixtures establish reader behavior, never official authority.
"""
from copy import deepcopy
from decimal import Decimal

from models import DebtTimeline
from test_deployment_fiscal_debt_20261105_postgres import owned_fiscal_debt_pg
from test_refresh_review_debt import document, freshness, run_source
from seeding.domains.debt_timeline.publication import debt_qualifications, public_debt_rows


def test_actual_pg_conflicting_retained_total_is_withheld_without_deleting_history(
    owned_fiscal_debt_pg, seed_country, tmp_path, monkeypatch,
):
    db = owned_fiscal_debt_pg
    run_source(db, tmp_path/'accepted', monkeypatch)
    row = db.query(DebtTimeline).filter_by(year=2025).one()
    assert debt_qualifications(db, [row])[row.id]['total']['status'] == 'verified'
    original = row.total
    metadata = deepcopy(row.meta)
    proof = next(e for e in metadata['source_evidence'] if e['identity']['measure'] == 'total')
    digest = proof['receipt']['digest']
    proof['receipt']['digest'] = ('b' if digest[0] != 'b' else 'c') * 64
    row.meta = metadata
    db.commit()
    db.expire_all()
    row = db.query(DebtTimeline).filter_by(year=2025).one()
    qualifications = debt_qualifications(db, [row])[row.id]
    assert row.total == original == Decimal('1300000000000')
    assert qualifications['total']['status'] == 'conflicting'
    assert qualifications['total']['reason'] == 'receipt_digest_mismatch'
    result = public_debt_rows(db, [row])[row.id]
    assert result['total'] is None
    assert result['absent_reasons']['total'] == 'receipt_digest_mismatch'
    assert result['external'] == 520000000000
    assert result['domestic'] == 780000000000
    assert result['gdp'] == 10000000000000
    assert result['gdp_ratio'] is None
    assert db.query(DebtTimeline).filter_by(year=2025).one().total == original


def test_actual_pg_source_missing_stock_scalars_are_not_publication_values(
    owned_fiscal_debt_pg, seed_country,
):
    db = owned_fiscal_debt_pg
    row = DebtTimeline(year=2025, external=400e9, domestic=600e9, total=1000e9,
        gdp=2000e9, gdp_ratio=50, unit='KES', source_document_id=None)
    db.add(row)
    db.commit()
    q = debt_qualifications(db, [row])[row.id]
    assert q['total']['status'] == 'unavailable'
    assert q['total']['reason'] == 'source_document_missing'
    result = public_debt_rows(db, [row])[row.id]
    for field in ('external', 'domestic', 'total', 'gdp'):
        assert result[field] is None
        assert result['absent_reasons'][field] == 'source_document_missing'
    assert result['gdp_ratio'] is None
    assert row.total == Decimal('1000000000000')


def test_actual_pg_cited_historical_stock_keeps_its_qualified_quantity(
    owned_fiscal_debt_pg, seed_country,
):
    db = owned_fiscal_debt_pg
    source = document(db)
    row = DebtTimeline(year=2025, external=400e9, domestic=600e9, total=1000e9,
        gdp=None, gdp_ratio=None, unit='KES', source_document_id=source.id)
    db.add(row)
    db.commit()
    q = debt_qualifications(db, [row])[row.id]
    assert q['total']['status'] == 'qualified'
    assert q['total']['reason'] == 'historical_source_not_value_checked'
    result = public_debt_rows(db, [row])[row.id]
    assert result['total'] == 1000000000000
    assert result['external'] == 400000000000
    assert result['domestic'] == 600000000000
    assert result['gdp'] is None
    assert result['gdp_ratio'] is None
