import importlib.util
import json
from pathlib import Path
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


@pytest.mark.parametrize('package', ['pytesseract', 'numpy', 'Pillow', 'pypdfium2'])
def test_ocr_dependency_change_can_withdraw_a_cached_edition(tmp_path, monkeypatch, package):
    from importlib import metadata
    from seeding import pdf_download
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
    import pytesseract
    monkeypatch.setattr(pytesseract, 'get_tesseract_version', lambda: '5.5.0')
    monkeypatch.setattr(pytesseract, 'get_languages', lambda **k: ['eng'])
    client = SimpleNamespace(get=lambda *a, **k: SimpleNamespace(text=(
        '<a href="https://www.treasury.go.ke/Budget-Summary-FY-2026-27.pdf">Budget Summary</a>')))
    settings = SeedingSettings(_env_file=None, cache_path=tmp_path, parse_cache_enabled=True)
    first, _ = _fetch_budget_summary_editions(client, settings)
    assert len(first) == 1
    records[62]['text'] = 'Unsupported new engine output'
    original = metadata.version
    monkeypatch.setattr(metadata, 'version', lambda name: '99.0.0' if name == package else original(name))
    second, facts = _fetch_budget_summary_editions(client, settings)
    assert second == []
    assert next(iter(facts['budget_summary_editions'].values()))['status'].startswith('refused:')
