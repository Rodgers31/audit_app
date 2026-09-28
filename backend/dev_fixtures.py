"""Small, explicitly synthetic records for local UI development only.

Shared with the existing browser acceptance API. Never imported by production.
"""

from datetime import datetime, timezone

from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_as_text(element, compiler, **kw):
    return "TEXT"


def seed_local_fixture(db_module):
    from models import (
        Audit, Base, BudgetLine, Country, DocumentType, Entity, EntityType,
        FiscalPeriod, Severity, SourceDocument,
    )

    expected_tables = set(Base.metadata.tables)
    existing_tables = set(inspect(db_module.engine).get_table_names())
    if existing_tables:
        # Do not let create_all add tables to a database that was already in
        # use. The fixture's exact row counts are small enough to check at boot.
        if existing_tables != expected_tables:
            raise RuntimeError("Local fixture seeder refuses a database with other tables")
        expected_counts = {
            "countries": 1,
            "entities": 2,
            "fiscal_periods": 2,
            "source_documents": 2,
            "budget_lines": 2,
            "audits": 2,
        }
        with db_module.SessionLocal() as db:
            country = db.query(Country).one_or_none()
            if country is None or (country.meta or {}).get("fixture") != "auditgava-local-dev-v1":
                raise RuntimeError("Local fixture seeder refuses a database without its fixture marker")
            for table in Base.metadata.tables.values():
                count = db.execute(select(func.count()).select_from(table)).scalar_one()
                if count != expected_counts.get(table.name, 0):
                    raise RuntimeError("Local fixture seeder refuses unexpected rows")
            if any(not doc.title.startswith("Synthetic ") for doc in db.query(SourceDocument)):
                raise RuntimeError("Local fixture seeder refuses non-synthetic documents")
            if any(not audit.finding_text.startswith("Synthetic ") for audit in db.query(Audit)):
                raise RuntimeError("Local fixture seeder refuses non-synthetic findings")
        return

    Base.metadata.create_all(db_module.engine)
    with db_module.SessionLocal() as db:
        db.add(Country(
            id=1, iso_code="KEN", name="Kenya", currency="KES",
            timezone="Africa/Nairobi", default_locale="en_KE",
            meta={"fixture": "auditgava-local-dev-v1", "synthetic": True},
        ))
        for pk, name, code in [(47, "Nairobi County", "047"), (1, "Mombasa County", "001")]:
            db.add(Entity(
                id=pk, country_id=1, type=EntityType.COUNTY,
                canonical_name=name, slug=name.split()[0].lower(),
                meta={"county_code": code, "synthetic": True},
            ))
        for pk, label, year in [(1, "FY2024/25", 2024), (2, "FY2025/26 9M", 2025)]:
            db.add(FiscalPeriod(
                id=pk, country_id=1, label=label,
                start_date=datetime(year, 7, 1),
                end_date=datetime(year + 1, 3 if pk == 2 else 6, 30),
            ))
        now = datetime.now(timezone.utc)
        db.add(SourceDocument(
            id=1, country_id=1, publisher="Synthetic local fixture",
            title="Synthetic CBIRR browser acceptance publication",
            url="https://example.invalid/auditgava-local-budget.pdf",
            doc_type=DocumentType.BUDGET, fetch_date=now,
            meta={"publication_date": now.date().isoformat(), "synthetic": True},
        ))
        db.add(SourceDocument(
            id=2, country_id=1, publisher="Synthetic local fixture",
            title="Synthetic local audit findings",
            url="https://example.invalid/auditgava-local-audit.pdf",
            doc_type=DocumentType.AUDIT, fetch_date=now,
            meta={"synthetic": True},
        ))
        db.flush()
        for pk, period, amount in [(1, 1, 50_000_000_000), (2, 2, 100_000_000_000)]:
            db.add(BudgetLine(
                id=pk, entity_id=47, period_id=period, category="Total",
                line_type="total", allocated_amount=amount, actual_spent=0,
                currency="KES", source_document_id=1, publishable=True,
                page_ref="p. 1",
            ))
        db.add(Audit(
            id=1, entity_id=47, period_id=1,
            finding_text="Synthetic finding: documentation for one local test payment is incomplete.",
            severity=Severity.WARNING, source_document_id=2,
            page_ref="p. 2", publishable=True,
            audit_year=2024, audit_opinion="qualified",
            provenance=[{"status": "open", "category": "documentation"}],
        ))
        db.add(Audit(
            id=2, entity_id=47, period_id=2,
            finding_text="Synthetic withheld finding: this has no page citation.",
            severity=Severity.CRITICAL, source_document_id=2,
            page_ref=None, publishable=False,
            audit_year=2025, provenance=[{"status": "withheld"}],
        ))
        db.commit()


def block_external_http():
    """Keep fixture API requests from contacting publishers or Supabase."""
    import httpx
    import requests
    from urllib.parse import urlparse

    original_send = requests.Session.send
    original_async = httpx.AsyncHTTPTransport.handle_async_request
    original_sync = httpx.HTTPTransport.handle_request

    def send(self, request, **kwargs):
        if urlparse(request.url).hostname not in {"localhost", "127.0.0.1"}:
            raise requests.ConnectionError("External network disabled in local fixture API")
        return original_send(self, request, **kwargs)

    async def async_request(self, request):
        if request.url.host not in {"localhost", "127.0.0.1"}:
            raise httpx.ConnectError("External network disabled in local fixture API")
        return await original_async(self, request)

    def sync_request(self, request):
        if request.url.host not in {"localhost", "127.0.0.1"}:
            raise httpx.ConnectError("External network disabled in local fixture API")
        return original_sync(self, request)

    requests.Session.send = send
    httpx.AsyncHTTPTransport.handle_async_request = async_request
    httpx.HTTPTransport.handle_request = sync_request
