"""Historical KRA article shapes, with offline transport and owned PG only.

Selected paragraphs come from the existing retained-text fixture. This is a
source-shaped reconstruction, not another copy of the full official HTML.
Its labelled day is corroborated by the separately retained original article;
transport/acquisition/job clocks and changed-value controls remain synthetic.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from html import escape
from pathlib import Path
import re

import httpx
import pytest
from sqlalchemy import func, select

from models import IngestionJob, IngestionStatus, RevenueBySource
from seeding.config import SeedingSettings
from seeding.domains.revenue_by_source import fetcher, parser, writer
from seeding.generation_dispatch import dispatch_committed_generation
from seeding.native_financial_observations import read_native_financial_observation
from seeding.types import DomainRunContext
from services.figure_qualification import qualify_rows
from services.receipt_store import LocalReceiptStore
from social.models import SocialPost, SocialPostRevision, SocialPostTarget, SocialPublication
from test_b83_generation_postgres import pg
from test_native_financial_changes_postgres import enable

URL = 'https://www.kra.go.ke/news-center/press-release/2235-kra-grows-revenue-by-6-8-despite-tough-economic-environment-4'
PUBLISHED = {'PAYE': '560.963', 'Corporation Tax': '304.833', 'VAT': '327.336',
             'Excise Duty': '69.385', 'Customs & Import Duty': '879.329'}
PREFIXES = {'PAYE': 'Pay As You Earn (P.A.YE):', 'Corporation Tax': 'Corporation Tax:',
            'VAT': 'Domestic VAT:', 'Excise Duty': 'Domestic Excise',
            'Customs & Import Duty': 'Customs Revenue recorded'}


def retained_paragraph(prefix):
    path = Path(__file__).parents[1] / 'fixtures/kra/fy2024_25_press_release.txt'
    lines = [' '.join(line.split()) for line in path.read_text().splitlines()]
    matches = [line for line in lines if line.startswith(prefix)]
    assert len(matches) == 1, (prefix, len(matches))
    return matches[0]


def paragraph(text, *, style='text-align: justify;', attrs=''):
    # Strong emphasis splits text nodes just as in the publisher HTML.
    html = re.sub(r'(Kshs\.?\s*[\d,.]+\s*(?:Billion|Trillion)\.?)',
                  r'<strong>\1</strong>', escape(text))
    return f'<p style="{style}"{attrs}>{html}</p>'


def article(*, paye='560.963', change=None):
    lead = retained_paragraph('The Kenya Revenue Authority (KRA) has surpassed')
    content = [paragraph(lead),
               paragraph(retained_paragraph('The performance is a growth')),
               '<p><strong><u>Economic Environment</u></strong></p>',
               paragraph(retained_paragraph('The revenue performance reflects')),
               '<p><strong><u>Revenue Performance for FY 2024/25</u></strong></p>',
               '<ol start="3"><li><strong>Domestic and Customs Revenue Performance</strong></li></ol>',
               paragraph(retained_paragraph('Domestic Revenues registered')),
               paragraph(retained_paragraph(PREFIXES['Customs & Import Duty'])),
               '<p><strong><u>Performance of Key Tax Heads</u></strong></p>']
    for head in ('VAT', 'PAYE', 'Corporation Tax', 'Excise Duty'):
        text = retained_paragraph(PREFIXES[head])
        if head == 'PAYE':
            text = text.replace('560.963', paye)
            style, attrs = 'text-align: justify;', ''
            if change == 'half_year': text += ' These collections cover only the first half of the financial year.'
            if change == 'target': text = text.replace('KRA collected', 'KRA targeted')
            if change == 'month': text += ' These collections are for July only.'
            if change == 'claim_old_fy': text = text.replace('from P.A.Y.E,', 'from P.A.Y.E in FY 2023/2024,')
            if change == 'claim_month': text = text.replace('from P.A.Y.E,', 'from P.A.Y.E in July 2024,')
            if change in ('claim_q1', 'claim_h1'):
                period = 'Q1' if change == 'claim_q1' else 'H1'
                text = text.replace('Despite the slow growth,', f'These collections cover {period}. Despite the slow growth,')
            if change and change.startswith('style:'): style = change.removeprefix('style:')
            if change == 'hidden': attrs = ' hidden'
            if change == 'aria_hidden': attrs = ' aria-hidden="true"'
            if change == 'unknown_class': attrs = ' class="unknown-visibility"'
            rendered = paragraph(text, style=style, attrs=attrs)
            content.append(rendered)
            if change == 'duplicate': content.append(rendered)
        else:
            content.append(paragraph(text))
        if head == 'VAT':
            content.append(paragraph(retained_paragraph('Betting Taxes:')))
    content.append(paragraph(retained_paragraph('Significant amounts of adjustment vouchers')))
    body = '<div class="blog-content">' + '\n'.join(content) + '</div>'
    body += '<div class="bottom-wrapper"><p>PRESS RELEASE 10/07/2025</p></div>'
    if change == 'missing_date': body = body.replace('PRESS RELEASE 10/07/2025', 'Updated July 2025')
    if change == 'future_date': body = body.replace('10/07/2025', '10/07/2099')
    if change == 'duplicate_date': body += '<div class="bottom-wrapper"><p>PRESS RELEASE 10/07/2025</p></div>'
    if change == 'wrong_period': body = body.replace('Financial Year 2024/2025', 'Financial Year 2024/2026')
    if change == 'quarterly_lead': body = body.replace('for the Financial Year 2024/2025', 'for the first quarter of the Financial Year 2024/2025')
    if change == 'missing_heading': body = body.replace('Performance of Key Tax Heads', 'Unreviewed predictions')
    return body.encode()


class Publisher:
    def __init__(self, tmp_path, body):
        self.receipt_store = LocalReceiptStore(tmp_path/'receipts')
        self.body = body

    def get(self, url, **kwargs):
        assert url == URL, 'This fixture permits one exact inert source only'
        return httpx.Response(200, content=self.body, headers={'content-type': 'text/html'},
                              request=httpx.Request('GET', url))


def test_retained_article_shape_binds_annual_cells_not_targets_or_halfyears(tmp_path):
    release = fetcher._read_release(Publisher(tmp_path, article()), URL, None)
    assert release.native_report_authority.value['published_on'] == '2025-07-10'
    assert set(release.heads) >= set(PUBLISHED)
    for head, amount in PUBLISHED.items():
        figure = release.heads[head]
        assert figure.raw_amount is not None, head
        assert Decimal(figure.raw_amount) == Decimal(amount)*Decimal(10**9)
        assert figure.locator['head'] == head
    # Neither the VAT half-years, Corporation target, nor voucher distractors.
    assert not ({Decimal(h.raw_amount) for h in release.heads.values() if h.raw_amount is not None}
                & {Decimal(v)*Decimal(10**9) for v in ('148.374','178.962','321.080','28.622','10.422','6.510')})


def ingest_article(factory, tmp_path, monkeypatch, *, paye='560.963', change=None):
    client = Publisher(tmp_path, article(paye=paye, change=change))
    with factory.begin() as db:
        job = IngestionJob(domain='revenue_by_source', status=IngestionStatus.RUNNING,
            dry_run=False, started_at=datetime.now(timezone.utc), errors=[], meta={'source_mode': 'live'})
        db.add(job); db.flush(); identity = job.id
        release = fetcher._read_release(client, URL, None)
        monkeypatch.setattr(fetcher, 'discover_kra_releases', lambda *a: ([release], release.fiscal_year, release.url))
        payload, status = fetcher._apply_kra_live([], client, SeedingSettings())
        assert status.startswith('promoted'), status
        stats = writer.persist_revenue_records(db, parser.parse_revenue_payload(payload),
            SeedingSettings(), DomainRunContext(None, False, identity))
        assert not stats.errors, stats.errors
        job.status = IngestionStatus.COMPLETED; job.finished_at = datetime.now(timezone.utc)
    return identity


def test_article_shape_current_pg_baseline_reacquire_correction_and_replay(pg, tmp_path, monkeypatch):
    factory, _ = pg; enable(factory, monkeypatch)
    first = ingest_article(factory, tmp_path, monkeypatch)
    with factory() as db:
        rows = list(db.scalars(select(RevenueBySource)))
        qualified = qualify_rows(db, 'revenue_by_source', rows)
        for row in rows:
            if row.revenue_type not in PUBLISHED: continue
            assert qualified[row.id]['amount_billion_kes']['status'] == 'verified', row.revenue_type
            expected = Decimal(PUBLISHED[row.revenue_type]).quantize(Decimal('.1'), rounding=ROUND_HALF_UP)
            assert row.amount_billion_kes == expected
    def run(job):
        return dispatch_committed_generation(factory, domain='revenue_by_source',
            ingestion_id=job, dry_run=False, include_reports=False)
    initial = run(first)
    assert initial['baselines'] == 5 and initial['drafts_created'] == 0, initial
    same = run(ingest_article(factory, tmp_path, monkeypatch))
    assert same['unchanged'] == 5 and same['drafts_created'] == 0, same
    # Synthetic correction: no claim that KRA published this changed value.
    correction = ingest_article(factory, tmp_path, monkeypatch, paye='561.963')
    changed = run(correction)
    assert changed['drafts_created'] == 1 and changed['unchanged'] == 4, changed
    replay = run(correction)
    assert replay['drafts_created'] == 0 and replay['unchanged'] == 5, replay
    with factory() as db:
        posts = list(db.scalars(select(SocialPost))); assert len(posts) == 1
        assert posts[0].editorial_state == 'pending_review'
        revision = db.get(SocialPostRevision, posts[0].current_revision_id)
        fact = revision.evidence_snapshot['source']['facts'][0]
        assert fact['metric'] == 'Revenue collected: PAYE'
        assert Decimal(fact['value']) == Decimal('562.0') and fact['scale'] == 'billions'
        assert fact['published_on'] == '2025-07-10' and fact['document_url'] == URL
        for model in (SocialPostTarget, SocialPublication):
            assert db.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize('change', [
    'style:display:none', 'style:visibility:hidden', 'style:text-align: justify; display:none',
    'style:color:white', 'style:background:red', 'hidden', 'aria_hidden', 'unknown_class',
    'style:text-align: justify\x1f',
    'duplicate', 'half_year', 'month', 'target', 'missing_heading', 'claim_old_fy', 'claim_month',
    'claim_q1', 'claim_h1',
])
def test_article_head_ambiguity_hidden_css_and_nonannual_scope_refuse(tmp_path, change):
    release = fetcher._read_release(Publisher(tmp_path, article(change=change)), URL, None)
    assert release is None or release.heads.get('PAYE') is None or release.heads['PAYE'].raw_amount is None


@pytest.mark.parametrize('change', ['missing_date','future_date','duplicate_date','wrong_period','quarterly_lead'])
def test_article_missing_or_ambiguous_publication_and_period_never_admit_cells(tmp_path, change):
    release = fetcher._read_release(Publisher(tmp_path, article(change=change)), URL, None)
    assert release is None or (release.native_report_authority is None and
                              all(h.raw_amount is None for h in release.heads.values()))


@pytest.mark.parametrize('head', list(PUBLISHED))
@pytest.mark.parametrize('position', ['claim', 'tail'])
def test_every_article_head_refuses_another_period(tmp_path, head, position):
    original = retained_paragraph(PREFIXES[head])
    if position == 'claim':
        # The amount itself is assigned to a different FY, not a comparison.
        altered = original.replace(PUBLISHED[head]+' Billion',
            PUBLISHED[head]+' Billion in FY 2023/2024', 1)
    else:
        altered = original+' These collections relate to July 2024.'
    body = article().replace(paragraph(original).encode(), paragraph(altered).encode())
    assert body != article()
    release = fetcher._read_release(Publisher(tmp_path, body), URL, None)
    assert release is not None and release.heads[head].raw_amount is None


@pytest.mark.parametrize('head', list(PUBLISHED))
@pytest.mark.parametrize('markup', ['paragraph', 'bare_text'])
def test_unknown_section_qualification_cannot_lend_annual_scope(tmp_path, head, markup):
    target = paragraph(retained_paragraph(PREFIXES[head])).encode()
    text = 'The following collections cover Q1.'
    qualifier = paragraph(text).encode() if markup == 'paragraph' else text.encode()
    body = article().replace(target, qualifier+target)
    assert body != article()
    release = fetcher._read_release(Publisher(tmp_path, body), URL, None)
    assert release is not None and release.heads[head].raw_amount is None


def test_unknown_list_cannot_reopen_an_annual_section(tmp_path):
    target = b'<ol start="3">'
    body = article().replace(target, b'<ol><li>The following collections cover Q1.</li></ol>'+target)
    release = fetcher._read_release(Publisher(tmp_path, body), URL, None)
    assert release is not None and release.heads['Customs & Import Duty'].raw_amount is None


def test_section_whitespace_and_comments_preserve_qualified_cells(tmp_path):
    body = article().replace(b'<p', b'\n <!-- presentation comment --> \t <p')
    release = fetcher._read_release(Publisher(tmp_path, body), URL, None)
    assert release is not None
    assert all(release.heads[head].raw_amount is not None for head in PUBLISHED)


@pytest.mark.parametrize('change', ['claim_old_fy', 'claim_month'])
def test_article_claim_local_period_refuses_committed_financial_fact(pg, tmp_path, monkeypatch, change):
    from seeding.source_observations import SourceObservationUnavailable
    factory, _ = pg; enable(factory, monkeypatch)
    job = ingest_article(factory, tmp_path, monkeypatch, change=change)
    with factory() as db:
        record = db.scalar(select(RevenueBySource.id).where(RevenueBySource.revenue_type == 'PAYE'))
    with pytest.raises(SourceObservationUnavailable):
        read_native_financial_observation(factory, record_id=record, ingestion_id=job, domain='revenue_by_source')
