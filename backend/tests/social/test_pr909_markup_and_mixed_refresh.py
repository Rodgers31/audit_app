"""Publisher syntax and fixture fallbacks retain their own refusal boundaries."""
from datetime import datetime, timezone

import pytest

from seeding.native_report_authority import capture_kra_release
from seeding.staleness import FAIL, WARN, check_ingestion_freshness
from test_b86_native_authority import HTML, receipt
from test_partial_refresh_reporting import _Session, _job


@pytest.mark.parametrize('body', [
    HTML.replace(b'</p>', b'', 1),
    HTML.replace(b'</p>', b'</section>', 1),
    HTML.rsplit(b'</div>', 1)[0],
    b'</p>' + HTML,
    HTML.replace(b'The Kenya', b'<strong>The Kenya', 1),
    HTML + b'<!-- unclosed',
    HTML + b'<div',
    HTML + b'<',
    HTML + b'</br>',
    HTML + b'<section/>',
    HTML.replace(b'</p>', b'</p ignored>', 1),
    HTML.replace(b'<p>', b'<p/class="">', 1),
    HTML.replace(b'<p>', b'<p style="text-align: justify;"class="">', 1),
    HTML.replace(b'<div class="blog-content">', b'<div/class="blog-content">'),
    HTML.replace(b'<div class="blog-content">', b'<div class="blog-content"aria-hidden="false">'),
    HTML + b'<section/class=""></section>',
], ids=['missing-paragraph-close', 'mismatched-close', 'missing-container-close',
        'orphan-close', 'unclosed-inline', 'unfinished-comment', 'unfinished-tag',
        'unfinished-opener', 'void-end-tag', 'nonvoid-self-close',
        'end-tag-attributes', 'missing-tag-separator', 'missing-attribute-separator',
        'container-solidus', 'container-attribute-separator', 'sibling-solidus'])
def test_repaired_markup_cannot_establish_kra_authority(tmp_path, body):
    proof, reason = capture_kra_release(receipt(tmp_path, body))
    assert proof is None and reason == 'native_report_date_or_scope_unavailable'


@pytest.mark.parametrize('body', [
    HTML,
    b'<!DOCTYPE html>' + HTML + b'<!-- ordinary layout -->',
    HTML + b'<hr><br/>',
    HTML + b'<section><p>Other <strong>visible</strong> text.</p></section>',
], ids=['original', 'doctype-comment', 'void-tags', 'balanced-sibling'])
def test_explicit_balanced_kra_profile_stays_eligible(tmp_path, body):
    proof, reason = capture_kra_release(receipt(tmp_path, body))
    assert reason is None and proof.value['published_on'] == '2025-07-10'


@pytest.mark.parametrize('order', [False, True], ids=['fixture-first', 'partial-first'])
@pytest.mark.parametrize('fixture_reason,level', [
    ('publisher_unavailable', FAIL), ('no_live_source', WARN),
    ('fixture_superseded', WARN), (None, FAIL),
])
def test_mixed_window_preserves_fixture_count_reason_and_severity(order, fixture_reason, level):
    fixture = _job('fiscal_summary', mode='fixture', job_id=1)
    if fixture_reason is None:
        fixture.meta.pop('source_fallback_reason')
    else:
        fixture.meta['source_fallback_reason'] = fixture_reason
    partial = _job('fiscal_summary', job_id=2)
    jobs = [partial, fixture] if order else [fixture, partial]
    findings = check_ingestion_freshness(_Session(jobs),
        now=datetime(2026, 11, 4, 3, tzinfo=timezone.utc), domains=['fiscal_summary'])
    assert len(findings) == 1
    finding = findings[0]
    assert finding.level == level
    assert '1/2 partial' in finding.message and '1/2 FIXTURE' in finding.message
    assert (fixture_reason or 'unrecorded') in finding.message
