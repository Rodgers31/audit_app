"""Whitespace-only operator evidence must never satisfy a release CHECK."""
from datetime import datetime, timezone
import os
from uuid import uuid4
from urllib.parse import urlsplit

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.pool import NullPool

from models import AdminAuditLog, EtlDispatchCommand, IngestionJob, SeedingDomainClaim


@compiles(JSONB, "sqlite")
def jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


BLANKS = ["", " ", "\t", "\n", "\r\n\t", "\u00a0", "\u2003", "\u202f", "\u3000",
          "\x1c\x1d\x1e\x1f", "".join(chr(i) for i in range(0x110000) if chr(i).isspace())]


@pytest.fixture(params=["sqlite", "postgresql"])
def storage(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")
        for model in (AdminAuditLog, IngestionJob, EtlDispatchCommand, SeedingDomainClaim):
            model.__table__.create(engine)
    else:
        url = os.environ["BATCH9_RECONCILIATION_DATABASE_URL"]
        parsed = urlsplit(url)
        assert (parsed.hostname == "127.0.0.1" and parsed.port is not None and
                parsed.path.startswith(("/batch9-reconciliation-", "/batch9-review-592-"))
                and not parsed.query and not parsed.fragment), "Explicit owned target required"
        engine = create_engine(url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.mark.parametrize("field", ["reconciled_by", "reconciliation"])
@pytest.mark.parametrize("blank", BLANKS)
def test_blank_reconciliation_cannot_release(storage, field, blank):
    now = datetime.now(timezone.utc)
    values = dict(id=uuid4(), domain="batch9-blank", kind="native", acquired_at=now,
                  entered_at=now, entry_id=uuid4(), released_at=now,
                  reconciled_by="operator", reconciliation="effects examined")
    values[field] = blank
    with pytest.raises(IntegrityError, match="ck_seeding_claim_reconciliation"):
        with storage.begin() as connection:
            connection.execute(SeedingDomainClaim.__table__.insert().values(**values))
            # A red baseline insert must roll back too; no stranded fixture rows.
            raise AssertionError("whitespace-only evidence was accepted")


def test_meaningful_unicode_reconciliation_retains_history(storage):
    now, identity = datetime.now(timezone.utc), uuid4()
    with storage.begin() as connection:
        connection.execute(SeedingDomainClaim.__table__.insert().values(
            id=identity, domain="batch9-unicode", kind="native", acquired_at=now,
            entered_at=now, entry_id=uuid4(), released_at=now,
            reconciled_by="\u2003opérateur\t", reconciliation="\n核验 effects\u00a0"))
    with storage.begin() as connection:
        row = connection.execute(SeedingDomainClaim.__table__.select().where(SeedingDomainClaim.id == identity)).one()
        assert row.returned_at is None and row.job_id is None
        connection.execute(SeedingDomainClaim.__table__.delete().where(SeedingDomainClaim.id == identity))
