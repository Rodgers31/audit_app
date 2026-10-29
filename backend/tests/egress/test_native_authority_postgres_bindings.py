"""Present JSON null/false/zero/empty bindings are keys, never absent proofs."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from harness import seed_country
from models import SourceDocument, DocumentType, DocumentStatus
from seeding.native_report_authority import KEY, DOMAINS, persist_native_report
from seeding.types import DomainRunContext


@pytest.mark.parametrize("domain", list(DOMAINS))
@pytest.mark.parametrize("binding", [None, False, 0, ""], ids=["null", "false", "zero", "empty-string"])
def test_postgres_present_falsy_bindings_are_removed_without_losing_siblings(pg_fixture, domain, binding):
    engine, _ = pg_fixture
    country_id, _ = seed_country(engine)
    original = {"keep": {"large": "x" * 65536}, KEY: {domain: binding, "sibling": {"retained": True}}}
    with Session(engine) as db:
        source = SourceDocument(country_id=country_id, publisher="Existing publisher", title="Retained source",
            url="https://cob.go.ke/retained.pdf", doc_type=DocumentType.REPORT,
            status=DocumentStatus.FAILED, fetch_date=datetime.now(timezone.utc), meta=deepcopy(original))
        db.add(source)
        db.commit()
        identity = source.id
        persist_native_report(db, source, None, context=DomainRunContext(None, False), domain=domain)
        assert "meta" not in source.__dict__
        db.commit()
        expected = deepcopy(original)
        del expected[KEY][domain]
        assert db.scalar(select(SourceDocument.meta).where(SourceDocument.id == identity)) == expected
