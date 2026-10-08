"""Retained-byte parser -> real PostgreSQL writer -> metadata read controls."""
from contextlib import nullcontext
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Country, GDPData, PovertyIndex, Extraction
from services.receipt_store import LocalReceiptStore
from services.response_receipts import capture_response
from seeding.config import SeedingSettings
from seeding.http_client import SeedingHttpClient
from seeding.observations import worldbank_observations
from seeding.domains import national_gdp
from seeding.types import DomainRunContext
from test_national_gdp_source_creation import pg

GDP = Path(__file__).parent / 'fixtures/worldbank_gdp_2022.json'


def response(body, *, status=200, content_type='application/json'):
    return httpx.Response(status, content=body, headers={'content-type': content_type},
        request=httpx.Request('GET', 'https://api.worldbank.org/v2/country/KEN/indicator/NY.GDP.MKTP.CN?format=json'))


def parse(resp, store):
    client = type('Client', (), {'receipt_store': store})()
    return worldbank_observations(resp, client, indicator='NY.GDP.MKTP.CN',
        measure='gdp_value', unit='KES', quantum='1', basis='current_prices')


def test_cas_exact_readback_reuse_and_changed_bytes_same_url(tmp_path):
    store = LocalReceiptStore(tmp_path)
    original = GDP.read_bytes()
    first = capture_response(response(original), store)
    second = capture_response(response(original), store)
    assert first['digest'] == second['digest'] == hashlib.sha256(original).hexdigest()
    assert store.read(first['digest']) == original
    assert len(list(tmp_path.glob('*/*'))) == 1
    changed = original.replace(b'13489642000000', b'13489642000001')
    third = capture_response(response(changed), store)
    assert third['digest'] != first['digest']
    assert len(list(tmp_path.glob('*/*'))) == 2
    store._path(first['digest']).write_bytes(b'corrupted')
    with pytest.raises(ValueError):
        store.read(first['digest'])
    with pytest.raises(ValueError):
        store.put(original)


@pytest.mark.parametrize('digest', ['', '../anything', 'F'*64, None])
def test_store_rejects_unsafe_keys(tmp_path, digest):
    with pytest.raises(ValueError):
        LocalReceiptStore(tmp_path).read(digest)


@pytest.mark.parametrize('change', ['country', 'indicator', 'year', 'unit', 'partial', 'missing_value', 'bool', 'nan', 'negative', 'duplicate'])
def test_wrong_identity_or_partial_bytes_refuse(tmp_path, change):
    body = json.loads(GDP.read_bytes())
    row = body[1][0]
    if change == 'country': row['countryiso3code'] = 'UGA'
    if change == 'indicator': row['indicator']['id'] = 'SI.POV.GINI'
    if change == 'year': row['date'] = '2022-Q1'
    if change == 'unit': row['unit'] = 'USD'
    if change == 'partial': body[0]['pages'] = 2
    if change == 'missing_value': row.pop('value')
    if change == 'bool': row['value'] = True
    if change == 'nan': row['value'] = float('nan')
    if change == 'negative': row['value'] = -1
    if change == 'duplicate': body[1].append(row.copy()); body[0]['total'] = 2
    with pytest.raises(ValueError):
        parse(response(json.dumps(body).encode()), LocalReceiptStore(tmp_path))


@pytest.mark.parametrize('status,kind', [(206, 'application/json'), (500, 'application/json'), (200, 'text/html')])
def test_partial_transport_or_wrong_type_refuse(tmp_path, status, kind):
    with pytest.raises(ValueError):
        parse(response(GDP.read_bytes(), status=status, content_type=kind), LocalReceiptStore(tmp_path))


@pytest.mark.parametrize("error", [OSError, RuntimeError])
def test_storage_failure_preserves_value_without_stronger_evidence(tmp_path, error):
    class FailedStore:
        def put(self, body): raise error('owned disk unavailable')
    values = parse(response(GDP.read_bytes()), FailedStore())
    assert values[2022] == 13489642000000
    evidence = values.evidence[2022][0]
    assert evidence['checks']['bytes'] is False
    assert evidence['_response_receipt']['byte_check']['status'] == 'missing'
    assert 'owned disk unavailable' in evidence['_response_receipt']['failure_reason']


def test_precision_and_zero_gini_conversion(tmp_path):
    body = json.loads(GDP.read_bytes())
    row = body[1][0]
    row['indicator']['id'] = 'SI.POV.GINI'
    row['value'] = 38.75
    client = type('Client', (), {'receipt_store': LocalReceiptStore(tmp_path)})()
    parsed = worldbank_observations(response(json.dumps(body).encode()), client,
        indicator='SI.POV.GINI', measure='gini_coefficient', unit='coefficient',
        factor='0.01', quantum='0.001', maximum='100')
    assert parsed[2022] == Decimal('0.388')
    assert parsed.evidence[2022][0]['raw_value'] == '38.75'
    row['value'] = 0
    parsed = worldbank_observations(response(json.dumps(body).encode()), client,
        indicator='SI.POV.GINI', measure='gini_coefficient', unit='coefficient',
        factor='0.01', quantum='0.001', maximum='100')
    assert parsed[2022] == 0


def test_actual_fetch_writer_commit_reopen_one_response_many_rows(pg, tmp_path, monkeypatch):
    body = json.loads(GDP.read_bytes())
    body[1].append({**body[1][0], 'date': '2021', 'value': 12000000000000})
    body[0]['total'] = 2
    gdp_bytes = json.dumps(body).encode()
    def handler(request):
        indicator = request.url.path.rsplit('/', 1)[-1]
        if indicator == 'NY.GDP.MKTP.CN': content = gdp_bytes
        else:
            poverty = json.loads(GDP.read_bytes())
            poverty[1][0]['indicator']['id'] = indicator
            poverty[1][0]['value'] = 38.75 if indicator == 'SI.POV.GINI' else 0
            content = json.dumps(poverty).encode()
        return httpx.Response(200, content=content, headers={'content-type':'application/json'})
    settings = SeedingSettings(storage_path=tmp_path, cache_path=tmp_path, http_cache_enabled=False)
    monkeypatch.setattr(national_gdp, 'create_http_client', lambda settings:
        SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler))))
    with Session(pg) as db:
        db.add(Country(id=1, name='Kenya', iso_code='KEN', currency='KES', timezone='Africa/Nairobi', default_locale='en'))
        db.commit()
        result = national_gdp.run(db, settings, DomainRunContext(since=None, dry_run=False))
        assert not result.errors, result.errors
        db.commit()
    with Session(pg) as db:
        rows = db.scalars(select(GDPData).order_by(GDPData.year)).all()
        ids = [row.meta['source_evidence'][0]['receipt']['extraction_id'] for row in rows]
        assert len(rows) == 2 and ids[0] == ids[1]
        extraction = db.get(Extraction, ids[0])
        receipt = extraction.extracted_json['response_receipt']
        assert extraction.page_number is None
        assert receipt['digest'] == hashlib.sha256(gdp_bytes).hexdigest()
        assert LocalReceiptStore(tmp_path / 'response-receipts').read(receipt['digest']) == gdp_bytes
        assert 'value' not in receipt and 'body' not in receipt
        assert len(receipt['observations']) == 2
        assert len(json.dumps(extraction.extracted_json)) < 4096
        poverty = db.scalars(select(PovertyIndex)).one()
        assert poverty.poverty_headcount_rate == 0
        assert poverty.extreme_poverty_rate is None
        assert poverty.gini_coefficient == Decimal('0.388')
        measures = {e['identity']['measure']:e for e in poverty.meta['source_evidence']}
        assert measures['gini_coefficient']['receipt']['extraction_id'] != measures['poverty_headcount_rate']['receipt']['extraction_id']
        assert len(db.scalars(select(Extraction)).all()) == 3


def test_manifest_is_frozen_before_persistence(pg, tmp_path):
    from services.response_receipts import persist_evidence
    from test_national_gdp_source_creation import country
    values = parse(response(GDP.read_bytes()), LocalReceiptStore(tmp_path))
    e = values.evidence[2022][0]
    with Session(pg) as db:
        db.add(country()); db.flush()
        doc = national_gdp._ensure_gdp_source_document(db)
        bound = persist_evidence(db, doc, values.evidence[2022])
        identifier = bound[0]['receipt']['extraction_id']
        e['_response_receipt']['observations'][0]['raw_value'] = 'forged'
        db.commit()
    with Session(pg) as db:
        manifest = db.get(Extraction, identifier).extracted_json['response_receipt']['observations']
        assert manifest[0]['raw_value'] == '13489642000000'


def test_missing_bytes_and_invalid_transformations_do_not_pass(tmp_path):
    store = LocalReceiptStore(tmp_path)
    with pytest.raises(FileNotFoundError): store.read('a'*64)
    client = type('Client', (), {'receipt_store': store})()
    for factor, quantum in [('0','1'), ('-1','1'), ('NaN','1'), ('1','0'), ('1','Infinity')]:
        with pytest.raises(ValueError):
            worldbank_observations(response(GDP.read_bytes()), client, indicator='NY.GDP.MKTP.CN',
                measure='gdp_value', unit='KES', factor=factor, quantum=quantum)


def test_retained_real_cbk_html_writer_roundtrip(pg, tmp_path):
    from services.response_receipts import persist_evidence
    from seeding.domains.economic_indicators.cbk_inflation import fetch_cbk_inflation, CBK_INFLATION_URL
    from seeding.domains.economic_indicators.parser import parse_economic_payload
    from seeding.domains.economic_indicators.writer import persist_economic_records
    from models import EconomicIndicator
    from test_national_gdp_source_creation import country
    body = (Path(__file__).parent/'fixtures/cbk/inflation_rates_2026-09-26.html').read_bytes()
    settings = SeedingSettings(storage_path=tmp_path, cache_path=tmp_path, http_cache_enabled=False)
    with SeedingHttpClient(settings, client=httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200, content=body, headers={'content-type':'text/html'})))) as client:
        result = fetch_cbk_inflation(client)
    # The swapped June2024 source cell remains rejected, not receipt upgraded.
    assert any(period == '2024-06' for period, reason in result.rejected)
    selected = [r for r in result.records if r['reference_month'] in ('2023-06','2024-01','2025-01')]
    with Session(pg) as db:
        db.add(country()); db.commit()
        stats = persist_economic_records(db, parse_economic_payload(selected), settings, DomainRunContext(since=None,dry_run=False))
        assert stats.created == 3 and not stats.errors
        db.commit()
    with Session(pg) as db:
        rows = db.scalars(select(EconomicIndicator)).all()
        assert {str(row.value) for row in rows} == {'7.88','6.85','3.28'}
        ids = {row.meta['source_evidence'][0]['receipt']['extraction_id'] for row in rows}
        assert len(ids) == 1
        receipt = db.get(Extraction, ids.pop()).extracted_json['response_receipt']
        assert len(receipt['observations']) == len(result.records)
        assert LocalReceiptStore(tmp_path/'response-receipts').read(receipt['digest']) == body


def test_retained_real_kra_dashboard_fetch_parser_writer(pg, tmp_path):
    import gzip
    from seeding.domains.revenue_by_source.fetcher import _read_release, _overlay_kra_release
    from seeding.domains.revenue_by_source.parser import parse_revenue_payload
    from seeding.domains.revenue_by_source.writer import persist_revenue_records
    from models import RevenueBySource
    from test_national_gdp_source_creation import country
    base = Path(__file__).parent/'fixtures/kra'
    page_url = 'https://www.kra.go.ke/annual-revenue-performance-fy-2025-2026'
    page = (base/'fy2025_26_annual_page.html').read_bytes()
    shell = (base/'fy2025_26_dashboard_shell.html').read_bytes()
    with gzip.open(base/'fy2025_26_dashboard_bundle.js.gz', 'rb') as f: bundle = f.read()
    def handler(request):
        body = page if str(request.url) == page_url else bundle if request.url.path.endswith('.js') else shell
        return httpx.Response(200, content=body, headers={'content-type':'application/javascript' if request.url.path.endswith('.js') else 'text/html'})
    settings = SeedingSettings(storage_path=tmp_path,cache_path=tmp_path,http_cache_enabled=False)
    with SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(handler))) as client:
        release = _read_release(client,page_url,None)
    assert release is not None and release.response_receipt['digest'] == hashlib.sha256(bundle).hexdigest()
    rows, status = _overlay_kra_release([],release)
    assert status.startswith('promoted')
    with Session(pg) as db:
        db.add(country()); db.commit()
        stats = persist_revenue_records(db,parse_revenue_payload(rows),settings,DomainRunContext(since=None,dry_run=False))
        assert not stats.errors, stats.errors
        db.commit()
    with Session(pg) as db:
        rows = db.scalars(select(RevenueBySource)).all()
        evidence = [r.meta['source_evidence'][0] for r in rows if r.meta.get('source_evidence')]
        assert len(evidence) == 5
        ids = {e['receipt']['extraction_id'] for e in evidence}
        assert len(ids) == 1
        receipt = db.get(Extraction,ids.pop()).extracted_json['response_receipt']
        assert len(receipt['observations']) == 5
        assert receipt['byte_size'] == len(bundle) == 628097
        for e in evidence:
            if 'char_start' in e['locator']:
                assert bundle.decode()[e['locator']['char_start']:e['locator']['char_end']] == e['raw_value']
        assert all(r.share_of_total_pct is None for r in rows)


def test_debt_gdp_retains_precision_and_independent_source(pg, tmp_path):
    from models import DebtTimeline
    from seeding.domains.debt_timeline.fetcher import _enrich_with_wb_gdp
    from seeding.domains.debt_timeline.parser import parse_debt_timeline_payload
    from seeding.domains.debt_timeline.writer import write_debt_timeline_records
    from test_national_gdp_source_creation import country
    settings = SeedingSettings(storage_path=tmp_path,cache_path=tmp_path,http_cache_enabled=False)
    with SeedingHttpClient(settings,client=httpx.Client(transport=httpx.MockTransport(lambda request:
        httpx.Response(200,content=GDP.read_bytes(),headers={'content-type':'application/json'})))) as client:
        payload = _enrich_with_wb_gdp({'timeline':[{'year':2022,'external':5,'domestic':5,'total':10,'source':'CBK debt fixture'}]},client)
    with Session(pg) as db:
        db.add(country()); db.commit()
        write_debt_timeline_records(db,parse_debt_timeline_payload(payload),{})
        db.commit()
    with Session(pg) as db:
        row = db.scalars(select(DebtTimeline)).one()
        assert row.gdp == Decimal('13489642000000')
        evidence = row.meta['source_evidence'][0]
        assert evidence['identity']['measure'] == 'gdp'
        assert evidence['receipt']['source_document_id'] != row.source_document_id
        assert evidence['value'] == str(row.gdp.quantize(Decimal('1')))
        assert all(e['identity']['measure'] not in {'total','gdp_ratio'} for e in row.meta['source_evidence'])
