"""Literal, independent source-admission controls; no live resources."""
import pytest
from seeding.native_financial_admission import SOURCE_ADMISSION_FLAG, source_admission_enabled


@pytest.mark.parametrize('raw', [None, '', 'false', 'TRUE', ' true ', '1', 'yes',
                               True, False, 1, 0, [], {}, float('nan'), float('inf')])
def test_ambiguous_source_flags_never_grant_admission(raw):
    assert source_admission_enabled({SOURCE_ADMISSION_FLAG: raw}) is False


def test_source_admission_requires_its_own_literal_flag():
    assert source_admission_enabled({}) is False
    assert source_admission_enabled({'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED': 'true'}) is False
    assert source_admission_enabled({SOURCE_ADMISSION_FLAG: 'true',
                                     'SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED': 'false'}) is True


@pytest.mark.parametrize('raw', ['', 'TRUE', ' true ', '1', 'yes'])
def test_process_environment_rejects_ambiguous_source_admission(monkeypatch, raw):
    monkeypatch.setenv(SOURCE_ADMISSION_FLAG, raw)
    assert source_admission_enabled() is False


@pytest.mark.parametrize('admit,generate', [('true', 'false'), ('false', 'true')])
def test_source_admission_reads_process_control_without_changing_generation(monkeypatch, admit, generate):
    monkeypatch.setenv(SOURCE_ADMISSION_FLAG, admit)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', generate)
    assert source_admission_enabled() is (admit == 'true')
    import os
    assert os.environ['SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED'] == generate


@pytest.mark.parametrize('domain', ['national_budget', 'pending_bills'])
@pytest.mark.parametrize('admit,generate', [('true', 'false'), ('false', 'true')])
@pytest.mark.parametrize('scope', ['live', 'dry_run', 'no_job'])
def test_only_admitted_live_sources_bypass_unsealed_parse_cache(monkeypatch, tmp_path, domain, admit, generate, scope):
    from types import SimpleNamespace
    from seeding.config import SeedingSettings
    from seeding.types import DomainRunContext
    import seeding.parse_cache as cache

    monkeypatch.setenv(SOURCE_ADMISSION_FLAG, admit)
    monkeypatch.setenv('SOCIAL_NATIVE_FINANCIAL_GENERATION_ENABLED', generate)
    monkeypatch.setenv('SEED_PENDING_BILLS_AGING_ENABLED', 'false')
    monkeypatch.setenv('SEED_PENDING_BILLS_ASSEMBLY_AGING_ENABLED', 'false')
    context = None if scope == 'no_job' else DomainRunContext(None, scope == 'dry_run', 23)
    settings = SeedingSettings(cache_path=tmp_path, live_pdf_fetch_enabled=True, parse_cache_enabled=True)
    calls = []
    class CacheBoundaryReached(Exception):
        pass
    def observe_cache(*args, **kwargs):
        calls.append(kwargs['enabled'])
        raise CacheBoundaryReached
    monkeypatch.setattr(cache, 'parse_with_cache', observe_cache)
    if domain == 'national_budget':
        import seeding.pdf_download as download
        from seeding.domains.national_budget.fetcher import AnnualReport, _fetch_annual_sector_expenditure
        monkeypatch.setattr(download, 'get_or_download_pdf', lambda *a, **kw: tmp_path/'owned.pdf')
        run = lambda: _fetch_annual_sector_expenditure(object(), settings,
            AnnualReport('https://cob.go.ke/owned.pdf', 'FY 2025/26', 2025), context=context)
    else:
        import seeding.cob_cbirr as download
        import seeding.pdf_parsers as parsers
        import seeding.domains.pending_bills.fetcher as pending
        monkeypatch.setattr(download, 'download_cbirr', lambda *a, **kw: SimpleNamespace(path=tmp_path/'owned.pdf'))
        monkeypatch.setattr(parsers, 'CbirrYearEndPayablesParser', lambda *a: SimpleNamespace(parse=lambda: []))
        monkeypatch.setattr(pending, 'year_end_cbirr_links', lambda *a: ['https://cob.go.ke/owned.pdf'])
        client = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(text='Owned listing transport'))
        run = lambda: pending.fetch_county_payables_payload(client, settings, context=context)
    if domain == 'pending_bills':
        with pytest.raises(pending.CountyPayablesUnavailable) as failure:
            run()
        assert isinstance(failure.value.__cause__, CacheBoundaryReached)
    else:
        with pytest.raises(CacheBoundaryReached):
            run()
    assert calls == [not (admit == 'true' and scope == 'live')]
