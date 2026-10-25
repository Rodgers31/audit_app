"""Owned loopback PostgreSQL fixture. No production defaults or credentials."""
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import Country, Entity, EntityType, IngestionJob, IngestionStatus
from seeding.exclusion import enter_domain
from seeding.types import DomainRunContext


@pytest.fixture
def borrowing_pg():
    raw = os.environ.get('B83_COUNTY_TEST_URL')
    if not raw:
        pytest.skip('Requires explicitly owned B83 loopback PostgreSQL fixture')
    url = make_url(raw)
    assert url.host == '127.0.0.1' and url.port == 55683 and url.database == 'b83_county'
    assert not any(os.environ.get(k) for k in ('PGSERVICE', 'PGSERVICEFILE', 'PGOPTIONS'))
    name = 'b83_county_' + uuid4().hex
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    with admin.connect() as c:
        assert c.scalar(text('SELECT count(*) FROM alembic_version')) == 1
        c.execute(text(f'CREATE DATABASE "{name}" TEMPLATE b83_county'))
    engine = create_engine(url.set(database=name))
    factory = sessionmaker(bind=engine)
    try:
        with factory.begin() as db:
            country = db.scalar(select(Country).where(Country.iso_code == 'KEN'))
            if country is None:
                country = Country(iso_code='KEN', name='Owned synthetic Kenya', currency='KES', timezone='Africa/Nairobi', default_locale='en')
                db.add(country); db.flush()
            for slug in ('kisii-county', 'mombasa-county'):
                db.add(Entity(country_id=country.id, type=EntityType.COUNTY, canonical_name=slug.replace('-', ' ').title(), slug=slug))
        yield engine, factory
    finally:
        engine.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
            assert c.scalar(text('SELECT count(*) FROM pg_database WHERE datname=:n'), {'n': name}) == 0
        admin.dispose()


@contextmanager
def owned(factory, dry_run=False):
    execution = enter_domain(factory, 'county_borrowing', dry_run)
    try:
        with factory.begin() as db:
            job = IngestionJob(domain='county_borrowing', status=IngestionStatus.RUNNING,
                dry_run=dry_run, started_at=datetime.now(timezone.utc), items_processed=0,
                items_created=0, items_updated=0, errors=[],
                meta={'since': None, 'seeding_claim_id': str(execution.identity)})
            db.add(job);db.flush();job_id=job.id
        yield DomainRunContext(since=None, dry_run=dry_run, job_id=job_id, ownership=execution)
    finally:
        execution.close()


def pdf_bytes(lines):
    # Small valid text PDF, entirely synthetic, independent of financial parsers.
    stream = 'BT /F1 10 Tf 20 760 Td '
    for line in lines:
        escaped = line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
        stream += '(' + escaped + ') Tj 0 -14 Td '
    stream += 'ET'
    content = stream.encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length '+str(len(content)).encode()+b' >>\nstream\n'+content+b'\nendstream']
    out=bytearray(b'%PDF-1.4\n'); offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(out));out.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
    xref=len(out);out.extend(b'xref\n0 6\n0000000000 65535 f \n')
    for offset in offsets[1:]:out.extend(f'{offset:010} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(out)
