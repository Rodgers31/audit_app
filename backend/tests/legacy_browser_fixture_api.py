"""Original browser suite's synthetic, loopback-only API. No provider access.

Uses production readers with a disposable SQLite database. Every fiscal amount,
finding and document here is invented solely for browser contracts, not Kenya data.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Also isolate direct Playwright/config invocation, which otherwise merges the
# parent's environment into webServer.env.
_allowed = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'PYTHONDONTWRITEBYTECODE') if k in os.environ}
os.environ.clear(); os.environ.update(_allowed)
# Disable both independent environment-file loaders BEFORE application imports.
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
import dotenv
dotenv.load_dotenv = lambda *a, **k: False
from pydantic_settings import BaseSettings
_original_init = BaseSettings.__init__
def _isolated_init(self, *args, **kwargs):
    kwargs['_env_file'] = None
    _original_init(self, *args, **kwargs)
BaseSettings.__init__ = _isolated_init
ROOT = Path(tempfile.mkdtemp(prefix='auditgava-legacy-browser-'))
os.environ.update(DATABASE_URL=f'sqlite:///{ROOT / "fixture.sqlite"}', REDIS_URL='',
                  ENVIRONMENT='test', SECRET_BACKEND='env', SECRET_KEY='synthetic-browser-secret',
                  AUTO_SEEDER_ENABLED='false', AUTO_WARMUP_ENABLED='false',
                  ENABLE_SEEDER='false', ENABLE_CACHE_WARMUP='false',
                  CACHE_GENERATION_FILE=str(ROOT / 'generation'), DISABLE_RATE_LIMIT='true',
                  CORS_ORIGINS='http://127.0.0.1:3141', REVALIDATE_SECRET='synthetic-browser-secret')
from dev_fixtures import block_external_http, seed_local_fixture, FIXTURE_TIMESTAMP
block_external_http()
import database
seed_local_fixture(database)
import main
from models import Audit, BudgetLine, Entity, EntityType, FiscalSummary, Severity
from services.county_identity import official_county_code

with database.SessionLocal() as db:
    # The base acceptance fixture deliberately has only two counties. Add the
    # full synthetic list so pagination, deep links and back navigation execute.
    for route_id, name in main.COUNTY_MAPPING.items():
        entity = db.query(Entity).filter(Entity.canonical_name == name + ' County').one_or_none()
        if entity is None:
            entity = Entity(country_id=1, type=EntityType.COUNTY, canonical_name=name + ' County',
                            slug=name.lower().replace(' ', '-'), alt_names=[],
                            meta={'county_code': official_county_code(name), 'synthetic': True},
                            created_at=FIXTURE_TIMESTAMP)
            db.add(entity); db.flush()
        for period, allocated in ((1, 8_000_000_000), (2, 10_000_000_000)):
            row = db.query(BudgetLine).filter_by(entity_id=entity.id, period_id=period, category='Total').one_or_none()
            if row is None:
                row = BudgetLine(entity_id=entity.id, period_id=period, category='Total', line_type='total',
                                 currency='KES', source_document_id=1, page_ref='p. 1', publishable=True,
                                 provenance=[], created_at=FIXTURE_TIMESTAMP)
                db.add(row)
            row.allocated_amount = allocated; row.actual_spent = allocated * 0.6
            row.committed_amount = 1_000_000_000
        # A cited finding with a publisher-stated
        # amount exercises audit tabs and preserves amount-coverage semantics.
        db.add(Audit(entity_id=entity.id, period_id=2, source_document_id=2, page_ref='p. 2',
                     finding_text='Synthetic browser finding: Unaccounted test payment of Kshs.1,000,000.',
                     amount=1_000_000, severity=Severity.WARNING, publishable=True,
                     audit_year=2025, audit_opinion='qualified', provenance=[],
                     created_at=FIXTURE_TIMESTAMP))
    # Deliberately simple synthetic totals: service 50 / ordinary revenue 100;
    # fiscal framework spending 150 = recurrent 90 + development 40 + transfers20.
    fw = dict(basis='treasury_fiscal_framework', identified_by='approved_budget',
              total_expenditure_billion=150, recurrent_billion=90, interest_payments_billion=30,
              development_billion=40, county_transfers_billion=20, county_equitable_share_billion=20,
              contingency_billion=0, total_revenue_incl_aia_billion=120, ordinary_revenue_billion=100,
              ministerial_aia_billion=20, grants_billion=5, fiscal_deficit_incl_grants_billion=25,
              total_financing_billion=25, net_foreign_financing_billion=10, net_domestic_financing_billion=15,
              adjustment_to_cash_basis_billion=0, statistical_discrepancy_billion=0,
              tax_revenue_billion=80, non_tax_revenue_billion=20,
              source={'title':'Synthetic browser fiscal framework','publisher':'Synthetic local fixture',
                      'page':'p. 1','url':'https://example.invalid/auditgava-local-budget.pdf'})
    for year, amount in (('FY 2024/25', 150), ('FY 2025/26', 180)):
        db.add(FiscalSummary(fiscal_year=year, appropriated_budget=amount*1e9, total_revenue=100e9,
                            tax_revenue=80e9, non_tax_revenue=20e9, total_borrowing=25e9,
                            debt_service_cost=50e9, debt_service_per_shilling=50,
                            development_spending=40e9, recurrent_spending=90e9, county_allocation=20e9,
                            unit='KES', source_document_id=1, page_ref='p. 1', publishable=True,
                            meta={'synthetic':True,'fiscal_framework':fw, 'split_basis':'treasury_fiscal_framework'},
                            created_at=FIXTURE_TIMESTAMP, updated_at=FIXTURE_TIMESTAMP))
    db.commit()
from contextlib import asynccontextmanager
@asynccontextmanager
async def _inert(app):
    yield
main.app.router.lifespan_context = _inert
main.app.router.on_startup.clear(); main.app.router.on_shutdown.clear()
assert not main.AUTO_SEEDER_ENABLED and not main._WARMUP_ENABLED
assert str(database.engine.url).startswith('sqlite:///')
@main.app.middleware('http')
async def absent_national_prefetch(request, call_next):
    # A successful prefetched query would hide browser-only hostile responses
    # behind its staleTime. Only national observation inputs are per-test.
    if request.url.path == '/api/v1/debt/national':
        from fastapi.responses import JSONResponse
        return JSONResponse({'status':'unavailable','reason':'synthetic_browser_prefetch_absence'}, status_code=503)
    return await call_next(request)
if __name__ == '__main__':
    import uvicorn
    print('RESOLVED synthetic=true DB=disposable-SQLite external-HTTP=blocked dotenv/Pydantic-files=disabled seeder/warmup=false API=127.0.0.1:8141', flush=True)
    try:
        uvicorn.run(main.app, host='127.0.0.1', port=8141)
    finally:
        import shutil
        shutil.rmtree(ROOT)
