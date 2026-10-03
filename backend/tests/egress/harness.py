"""Isolated PostgreSQL fixtures and decoded-result estimates; no production access."""
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from uuid import uuid4

from psycopg2.extensions import cursor as BaseCursor
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

from models import (Annotation, Base, BudgetLine, Country, Entity, EntityType, Extraction,
                    FiscalPeriod, IngestionJob, RevenueBySource, SourceDocument, User)
from seeding.domains.national_budget.parser import NationalBudgetRecord
from seeding.domains.revenue_by_source.parser import RevenueBySourceRecord


def local_url(value):
    try:
        url = make_url(value)
    except ArgumentError:
        raise ValueError('An explicit dedicated loopback database URL is required') from None
    if (url.drivername not in ('postgresql', 'postgresql+psycopg2') or
            url.host not in ('localhost', '127.0.0.1', '::1') or
            url.port != 62124 or url.database != 'social_worker_test'):
        raise ValueError('Use only the dedicated loopback social_worker_test database on port 62124')
    return url.set(drivername='postgresql+psycopg2')


def cell_bytes(value):
    """UTF-8 size of decoded values; excludes protocol, TLS and pooler overhead."""
    if value is None:
        return 0
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return len(str(value).encode('utf-8'))


@dataclass
class QuerySample:
    sql: str
    columns: tuple
    rows: int
    selected_value_bytes: int


@dataclass
class Probe:
    samples: list = field(default_factory=list)
    enabled: bool = False
    peak_connections: int = 0
    _active_connections: int = 0

    @contextmanager
    def capture(self):
        self.samples.clear()
        self.peak_connections = self._active_connections
        self.enabled = True
        try:
            yield self
        finally:
            self.enabled = False

    def selected(self, table):
        return [sample for sample in self.samples
                if sample.sql.lstrip().upper().startswith('SELECT') and
                ('FROM '+table) in sample.sql]

    def summary(self, samples=None):
        samples = self.samples if samples is None else samples
        return {'queries': len(samples), 'returned_rows': sum(s.rows for s in samples),
                'selected_value_bytes_estimate': sum(s.selected_value_bytes for s in samples),
                'peak_checked_out_connections': self.peak_connections}


def recording_cursor(probe):
    class Cursor(BaseCursor):
        def execute(self, query, variables=None):
            self._buffer = None
            self._position = 0
            result = super().execute(query, variables)
            if probe.enabled:
                columns = tuple(column.name for column in self.description) if self.description else ()
                self._buffer = super().fetchall() if self.description else None
                rows = self._buffer or ()
                sql = query.decode('utf-8') if isinstance(query, bytes) else str(query)
                probe.samples.append(QuerySample(sql, columns, len(rows),
                    sum(cell_bytes(value) for row in rows for value in row)))
            return result

        def fetchone(self):
            if self._buffer is None:
                return super().fetchone()
            if self._position == len(self._buffer):
                return None
            row = self._buffer[self._position]
            self._position += 1
            return row

        def fetchmany(self, size=None):
            if self._buffer is None:
                return super().fetchmany(size) if size is not None else super().fetchmany()
            size = self.arraysize if size is None else size
            rows = self._buffer[self._position:self._position+size]
            self._position += len(rows)
            return rows

        def fetchall(self):
            if self._buffer is None:
                return super().fetchall()
            rows = self._buffer[self._position:]
            self._position = len(self._buffer)
            return rows
    return Cursor


@contextmanager
def isolated_engine(value, *, social=False):
    url = local_url(value)
    schema = 'egress_fixture_'+uuid4().hex
    admin = create_engine(url, pool_size=1, max_overflow=0, hide_parameters=True,
                          connect_args={'connect_timeout': 5})
    engine = None
    try:
        with admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA '+schema))
        probe = Probe()
        engine = create_engine(url, pool_size=2, max_overflow=0, pool_timeout=5,
            pool_pre_ping=True, hide_parameters=True,
            connect_args={'connect_timeout': 5, 'options':'-csearch_path='+schema,
                          'cursor_factory':recording_cursor(probe)})
        @event.listens_for(engine, 'checkout')
        def checkout(*args):
            probe._active_connections += 1
            if probe.enabled:
                probe.peak_connections = max(probe.peak_connections, probe._active_connections)
        @event.listens_for(engine, 'checkin')
        def checkin(*args):
            probe._active_connections -= 1
        tables = [model.__table__ for model in (Country, Entity, FiscalPeriod, SourceDocument,
                   Extraction, BudgetLine, RevenueBySource, IngestionJob, User, Annotation)]
        if social:
            from social.models import SOCIAL_TABLES
            tables += list(SOCIAL_TABLES)
        Base.metadata.create_all(engine, tables=tables)
        yield engine, probe
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as conn:
            conn.execute(text('DROP SCHEMA IF EXISTS '+schema+' CASCADE'))
        admin.dispose()


def seed_country(engine):
    with Session(engine) as db:
        country = Country(iso_code='KEN',name='Kenya',currency='KES',timezone='Africa/Nairobi',default_locale='en',meta={})
        db.add(country)
        db.flush()
        entity = Entity(country_id=country.id,type=EntityType.NATIONAL,
                        canonical_name='National Government of Kenya',slug='national-government')
        db.add(entity)
        db.flush()
        result = country.id, entity.id
        db.commit()
    return result


def budget_records(count=20, *, source_count=2):
    return [NationalBudgetRecord(entity_slug='national-government',entity_name='National Government of Kenya',
        period_label='FY2025/26',start_date=date(2025,7,1),end_date=date(2026,6,30),
        category='Sector '+str(i),subcategory='Recurrent & Development',
        allocated_amount=Decimal(100+i),actual_spent=Decimal(50+i),committed_amount=None,
        currency='KES',source='Verified fixture report',source_url='https://fixture.invalid/budget/'+str(i%source_count),
        data_quality='official',notes='Fixture only',page_ref='p.'+str(i+1),
        provenance_extra={'measure':'expenditure','period':'annual'}) for i in range(count)]


def revenue_records(count=20, *, source_count=2):
    return [RevenueBySourceRecord(fiscal_year='FY2025/26',revenue_type='Type '+str(i),category='tax',
        amount_billion_kes=Decimal(i),target_billion_kes=Decimal(i+1),performance_pct=None,
        share_of_total_pct=None,yoy_growth_pct=None,
        source_url='https://fixture.invalid/revenue/'+str(i%source_count),
        metadata={'basis':'published','measure':'cash_received'},publisher='Declared publisher',
        source_title='Declared report '+str(i%source_count)) for i in range(count)]
