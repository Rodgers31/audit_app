import importlib.util
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from seeding.config import SeedingSettings
from seeding.domains.fiscal_summary import fiscal_framework as ff
from seeding.domains.fiscal_summary.fetcher import _fetch_budget_summary_editions


@pytest.mark.parametrize('enabled', [False, True])
def test_changed_extractor_can_withdraw_a_previously_cached_edition(tmp_path, monkeypatch, enabled):
    from seeding import pdf_download

    pdf = tmp_path / 'owned.pdf'
    pdf.write_bytes(b'%PDF-1.7\nowned cache input\n%%EOF')
    monkeypatch.setattr(pdf_download, 'get_or_download_pdf', lambda *a, **k: pdf)
    fixtures = Path(__file__).parent / 'fixtures/budget_summary/fy2026_27.json'
    doc = json.loads(fixtures.read_text())
    records = [dict(page=i, text=doc['pages'].get(str(i), ''))
               for i in range(1, doc['_source']['page_count'] + 1)]
    client = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text=(
        '<a href="https://www.treasury.go.ke/sites/default/files/'
        'Budget-Summary-FY-2026-27.pdf">Budget Summary</a>'
    )))
    settings = SeedingSettings(_env_file=None, cache_path=tmp_path,
                               parse_cache_enabled=enabled)

    def install(name, values):
        path = tmp_path / (name + '.py')
        path.write_text('def extract_page_texts(path):\n    return ' + repr(values) + '\n')
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(ff, 'extract_page_texts', module.extract_page_texts)

    install('first_extractor', records)
    first, _ = _fetch_budget_summary_editions(client, settings)
    assert [edition.fiscal_year for _, edition in first] == ['FY 2026/27']
    records[62]['text'] = 'Unsupported image layout'
    install('second_extractor', records)
    second, facts = _fetch_budget_summary_editions(client, settings)
    assert second == []
    assert next(iter(facts['budget_summary_editions'].values()))['status'].startswith('refused:')


@pytest.mark.parametrize('dependency', ['ocr_engine', 'worker_image', 'pdfplumber', 'pdfminer.six',
                                      'numpy', 'Pillow', 'pypdfium2'])
def test_ocr_dependency_change_can_withdraw_a_cached_edition(tmp_path, monkeypatch, dependency):
    from importlib import metadata
    from seeding import isolated_parser, native_ocr, pdf_download
    pdf = tmp_path / 'owned.pdf'
    pdf.write_bytes(b'%PDF-1.7\nowned dependency cache input\n%%EOF')
    monkeypatch.setattr(pdf_download, 'get_or_download_pdf', lambda *a, **k: pdf)
    doc = json.loads((Path(__file__).parent / 'fixtures/budget_summary/fy2026_27.json').read_text())
    records = [dict(page=i, text=doc['pages'].get(str(i), ''))
               for i in range(1, doc['_source']['page_count'] + 1)]
    path = tmp_path / 'owned_extractor.py'
    path.write_text('def extract_page_texts(path):\n    return RECORDS\n')
    spec = importlib.util.spec_from_file_location('owned_dependency_extractor', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RECORDS = records
    monkeypatch.setattr(ff, 'extract_page_texts', module.extract_page_texts)
    engine = ['5.5.0']
    monkeypatch.setattr(native_ocr, 'engine_identity', lambda: (engine[0], ['eng']))
    if dependency == 'worker_image':
        backend = Path(__file__).resolve().parents[1]
        source = tmp_path / 'source/backend'
        for relative in ('ingestion-runtime.lock.json', 'seeding/isolated_parser.py',
                         'seeding/parser_worker.py', 'seeding/native_ocr.py',
                         'seeding/native_parser_child.py'):
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(backend / relative, destination)
        monkeypatch.setenv('SEED_PARSER_ROOT', str(tmp_path))
    client = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text=(
        '<a href="https://www.treasury.go.ke/Budget-Summary-FY-2026-27.pdf">Budget Summary</a>')))
    settings = SeedingSettings(_env_file=None, cache_path=tmp_path, parse_cache_enabled=True)
    first, _ = _fetch_budget_summary_editions(client, settings)
    assert len(first) == 1
    records[62]['text'] = 'Unsupported new engine output'
    cached, _ = _fetch_budget_summary_editions(client, settings)
    assert cached == first
    if dependency == 'ocr_engine':
        engine[0] = '5.6.0'
    elif dependency == 'worker_image':
        monkeypatch.setattr(isolated_parser, 'IMAGE', 'sha256:' + '1' * 64)
    else:
        original = metadata.version
        monkeypatch.setattr(metadata, 'version', lambda name: '99.0.0' if name == dependency else original(name))
    second, facts = _fetch_budget_summary_editions(client, settings)
    assert second == []
    assert next(iter(facts['budget_summary_editions'].values()))['status'].startswith('refused:')
