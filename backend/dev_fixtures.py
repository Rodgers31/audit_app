"""Small, explicitly synthetic records for local UI development only.

Shared with the existing browser acceptance API. Never imported by production.
"""

from datetime import datetime

from sqlalchemy import func, inspect, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(JSONB, "sqlite")
def _jsonb_as_text(element, compiler, **kw):
    return "TEXT"


FIXTURE_TIMESTAMP = datetime(2026, 4, 1)


def _fixture_rows():
    from models import (
        Audit, BudgetLine, Country, DocumentStatus, DocumentType, Entity,
        EntityType, FiscalPeriod, Severity, SourceDocument,
    )

    stamp = FIXTURE_TIMESTAMP
    return {
        Country: [{
            "id": 1, "iso_code": "KEN", "name": "Kenya", "currency": "KES",
            "timezone": "Africa/Nairobi", "default_locale": "en_KE",
            "meta": {"fixture": "auditgava-local-dev-v1", "synthetic": True},
            "created_at": stamp,
        }],
        Entity: [
            {
                "id": pk, "country_id": 1, "type": EntityType.COUNTY,
                "canonical_name": name, "slug": name.split()[0].lower(),
                "alt_names": [], "meta": {"county_code": code, "synthetic": True},
                "created_at": stamp,
            }
            for pk, name, code in ((47, "Nairobi County", "047"), (1, "Mombasa County", "001"))
        ],
        FiscalPeriod: [
            {
                "id": pk, "country_id": 1, "label": label,
                "start_date": datetime(year, 7, 1),
                "end_date": datetime(year + 1, 3 if pk == 2 else 6, 30),
                "created_at": stamp,
            }
            for pk, label, year in ((1, "FY2024/25", 2024), (2, "FY2025/26 9M", 2025))
        ],
        SourceDocument: [
            {
                "id": 1, "country_id": 1, "publisher": "Synthetic local fixture",
                "title": "Synthetic CBIRR browser acceptance publication",
                "url": "https://example.invalid/auditgava-local-budget.pdf",
                "doc_type": DocumentType.BUDGET, "status": DocumentStatus.AVAILABLE,
                "fetch_date": stamp, "last_seen_at": stamp, "created_at": stamp,
                "meta": {"publication_date": stamp.date().isoformat(), "synthetic": True},
            },
            {
                "id": 2, "country_id": 1, "publisher": "Synthetic local fixture",
                "title": "Synthetic local audit findings",
                "url": "https://example.invalid/auditgava-local-audit.pdf",
                "doc_type": DocumentType.AUDIT, "status": DocumentStatus.AVAILABLE,
                "fetch_date": stamp, "last_seen_at": stamp, "created_at": stamp,
                "meta": {"synthetic": True, "extraction_stats": {"volume_kind": "executives"}},
            },
        ],
        BudgetLine: [
            {
                "id": pk, "entity_id": 47, "period_id": period, "category": "Total",
                "line_type": "total", "allocated_amount": amount, "actual_spent": 0,
                "currency": "KES", "source_document_id": 1, "publishable": True,
                "page_ref": "p. 1", "provenance": [], "created_at": stamp,
            }
            for pk, period, amount in ((1, 1, 50_000_000_000), (2, 2, 100_000_000_000))
        ],
        Audit: [
            {
                "id": 1, "entity_id": 47, "period_id": 1,
                "finding_text": "Synthetic finding: documentation for one local test payment is incomplete.",
                "severity": Severity.WARNING, "source_document_id": 2,
                "page_ref": "p. 2", "publishable": True,
                "audit_year": 2024, "audit_opinion": "qualified",
                "provenance": [{"status": "open", "category": "documentation"}],
                "created_at": stamp,
            },
            {
                "id": 2, "entity_id": 47, "period_id": 2,
                "finding_text": "Synthetic withheld finding: this has no page citation.",
                "severity": Severity.CRITICAL, "source_document_id": 2,
                "publishable": False, "audit_year": 2025,
                "provenance": [{"status": "withheld"}], "created_at": stamp,
            },
        ],
    }


def _verify_fixture_rows(db, fixture_rows):
    from models import BudgetLine

    for model, expected_rows in fixture_rows.items():
        observed = {row.id: row for row in db.query(model)}
        for expected in expected_rows:
            row = observed.get(expected["id"])
            if row is None:
                raise RuntimeError("Local fixture seeder refuses changed fixture IDs")
            for attribute in inspect(model).column_attrs:
                key = attribute.key
                actual = getattr(row, key)
                wanted = expected.get(key)
                # The browser acceptance control changes only this synthetic budget value.
                if model is BudgetLine and row.id == 2 and key == "allocated_amount":
                    if actual in (wanted, 125_000_000_000):
                        continue
                if actual != wanted:
                    raise RuntimeError(f"Local fixture seeder refuses changed {model.__tablename__}.{key}")


def seed_local_fixture(db_module):
    from models import Base

    fixture_rows = _fixture_rows()
    expected_tables = set(Base.metadata.tables)
    existing_tables = set(inspect(db_module.engine).get_table_names())
    if existing_tables:
        # Do not let create_all add tables to a database that was already in
        # use. The fixture's exact row counts are small enough to check at boot.
        if existing_tables != expected_tables:
            raise RuntimeError("Local fixture seeder refuses a database with other tables")
        expected_counts = {model.__tablename__: len(rows) for model, rows in fixture_rows.items()}
        with db_module.SessionLocal() as db:
            for table in Base.metadata.tables.values():
                count = db.execute(select(func.count()).select_from(table)).scalar_one()
                if count != expected_counts.get(table.name, 0):
                    raise RuntimeError("Local fixture seeder refuses unexpected rows")
            _verify_fixture_rows(db, fixture_rows)
        return

    Base.metadata.create_all(db_module.engine)
    with db_module.SessionLocal() as db:
        for model, rows in fixture_rows.items():
            db.add_all(model(**values) for values in rows)
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
