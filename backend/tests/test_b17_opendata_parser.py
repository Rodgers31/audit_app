"""Real official bytes and direct parser/transport/default-off boundaries."""
from datetime import datetime
from pathlib import Path
from decimal import Decimal, localcontext
from unittest.mock import MagicMock
import subprocess
import sys
import os
import pytest
from seeding.domains.opendata import parser, source
from seeding.config import SeedingSettings

FIXTURE = Path(__file__).parent / 'fixtures/opendata/Chapter-5-Public-Finance.xlsx'


def test_official_cells_missing_labels_and_discrepancy_preserved():
    data = parser.parse_publication(FIXTURE.read_bytes())
    assert len(data['rows']) == 48 and len(data['columns']) == 46
    assert (data['numeric_cells'], data['missing_cells']) == (2125, 83)
    assert data['rows'][-1]['cells']['AH'] == {'raw': '79703.149999999994', 'amount_million_2dp': '79703.15', 'missing': None}
    cross = {r['column']: r for r in data['reconciliations']}
    assert cross['AH']['sum_minus_published_million'] == '-0.01'
    assert cross['AH']['status'] == 'published_discrepancy'
    assert cross['AI']['sum_minus_published_million'] == '0.00'
    assert any(r['status'] == 'incomplete' for r in cross.values())
    assert sum(v['missing'] == 'dash' for r in data['rows'] for v in r['cells'].values()) == 53
    assert sum(v['missing'] == 'blank' for r in data['rows'] for v in r['cells'].values()) == 30
    specs = {r['column']: r for r in data['columns']}
    assert specs['AJ']['status'] == specs['Y']['status'] == 'provisional'
    assert specs['AI']['status'] == 'unspecified'
    assert specs['AK']['aggregation'] == 'published_total'
    assert data['footnotes']['A53'] == '+Revised '
    assert data['footnotes']['A54'] == '*Provisional '
    assert data['verification_status'] == 'source_extracted_not_publication_qualified'
    assert data['report_publication_month'] == '2026-04'
    assert data['workbook_publication_date'] is None and 'publication_month' not in data
    assert data['edition_notes'][0]['columns'] == ['V', 'AI', 'AT']
    assert data['unit_attribution']['bounded_knbs_sdmx_unconditional_context']['unit_mult'] == '6'


def test_fixed_edition_does_not_predict_a_future_publication():
    from seeding.source_registry import next_expected_window
    from datetime import date
    assert next_expected_window('knbs_county_revenue_2026_table_5_13', date(2026, 10, 18)) is None


@pytest.mark.parametrize('value', [None, False, True, 0, 1, '', b'', b'PK', b'x' * source.ARTIFACT_BYTES, bytearray(b'hello')])
def test_direct_parser_refuses_unknown_inputs(value):
    with pytest.raises(source.OpenDataSourceRefused):
        parser.parse_publication(value)


def test_hash_refusal_precedes_archive_processing(monkeypatch):
    def forbidden(*args):
        raise AssertionError('Unreviewed bytes reached archive processing')
    monkeypatch.setattr(parser, '_read_cells', forbidden)
    raw = bytearray(FIXTURE.read_bytes()); raw[-1] ^= 1
    with pytest.raises(source.OpenDataSourceRefused):
        parser.parse_publication(bytes(raw))


def test_host_decimal_context_does_not_change_financial_observations():
    expected = parser.parse_publication(FIXTURE.read_bytes())
    with localcontext() as context:
        context.prec = 2
        assert parser.parse_publication(FIXTURE.read_bytes()) == expected


@pytest.mark.parametrize('flag', [None, 0, 1, '', 'TRUE', 'yes', '1', ' false '])
def test_explicit_flag_rejects_coercion(flag):
    with pytest.raises(ValueError):
        SeedingSettings(opendata_ingestion_enabled=flag, _env_file=None)


@pytest.mark.parametrize('flag', [False, 'false', True, 'true'])
def test_flag_accepts_only_explicit_booleans(flag):
    assert SeedingSettings(opendata_ingestion_enabled=flag, _env_file=None).opendata_ingestion_enabled is (flag in (True, 'true'))


@pytest.mark.parametrize('mode', ['normal', 'redirect', 'status', 'type', 'oversize', 'late', 'empty'])
def test_bounded_official_transport(monkeypatch, mode):
    response = MagicMock()
    response.status_code = 302 if mode == 'redirect' else 503 if mode == 'status' else 200
    response.headers = {'content-type': 'text/html' if mode == 'type' else source.CONTENT_TYPE}
    response.iter_bytes.return_value = [b'x' * (source.MAX_BYTES + 1)] if mode == 'oversize' else [] if mode == 'empty' else [FIXTURE.read_bytes()]
    stream = MagicMock(); stream.__enter__.return_value = response
    client = MagicMock(); client.stream.return_value = stream
    constructor = MagicMock(); constructor.return_value.__enter__.return_value = client
    monkeypatch.setattr(source.httpx, 'Client', constructor)
    times = iter([0, source.MAX_SECONDS + 1, source.MAX_SECONDS + 1]) if mode == 'late' else iter([0, 0, 0])
    monkeypatch.setattr(source.time, 'monotonic', lambda: next(times))
    if mode in ('redirect', 'status', 'type', 'oversize', 'late'):
        with pytest.raises(source.OpenDataSourceRefused): source.fetch_publication()
    else:
        raw, fetched = source.fetch_publication()
        assert isinstance(fetched, datetime) and fetched.utcoffset() is not None
        if mode == 'normal': assert parser.parse_publication(raw)['numeric_cells'] == 2125
        else:
            with pytest.raises(source.OpenDataSourceRefused): parser.parse_publication(raw)
    assert constructor.call_args.kwargs == {'trust_env': False, 'follow_redirects': False, 'timeout': 10}
    if client.stream.called: assert client.stream.call_args.args[:2] == ('GET', source.URL)
