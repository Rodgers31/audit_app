/**
 * The homepage's only source of a debt-distress rating (issue #269).
 *
 * It must fail closed. A rating that has lost its URL, page or date is
 * indistinguishable from one somebody typed, and that was the defect: "High
 * risk of debt distress · IMF" came from `debt_to_gdp > 65`.
 */
import {
  dsaCitation,
  dsaHref,
  dsaIsAlarm,
  dsaSourceLabel,
  dsaVintageLabel,
  readDsaRating,
} from '@/lib/debt/dsaRating';

const IMF_DSA = {
  risk_of_external_debt_distress: 'High',
  overall_risk_of_debt_distress: 'High',
  granularity_in_the_risk_rating: 'Sustainable',
  source: {
    series: 'IMF Country Report No. 24/316',
    url: 'https://www.imf.org/-/media/files/publications/cr/2024/english/1kenea2024003-print-pdf.pdf',
    dsa_date: '2024-10-18',
    published: '2024-11-01',
    page: 132,
    page_label: 'PDF p. 132 (first page of the Debt Sustainability Analysis)',
  },
  latest_confirmed: { as_of: '2026-03-31', row: 27 },
};

const withSource = (patch: Record<string, unknown>) => ({
  imf_dsa: { ...IMF_DSA, source: { ...IMF_DSA.source, ...patch } },
});

describe('readDsaRating — a rating without its citation is not shown', () => {
  it.each([
    ['no payload', undefined],
    ['null', null],
    ['empty object', {}],
    // The shape production served before #269. `risk_level` was debt-to-GDP > 65.
    ['the old ratio-derived rating', { risk_level: 'High', assessment: 'The IMF classifies Kenya at high risk of debt distress.' }],
    ['no source', { imf_dsa: { ...IMF_DSA, source: undefined } }],
    ['no url', withSource({ url: '' })],
    ['no page', withSource({ page: undefined })],
    ['page not a number', withSource({ page: '132' })],
    ['no date', withSource({ dsa_date: undefined })],
    ['unparseable date', withSource({ dsa_date: 'October 2024' })],
    ['no series', withSource({ series: '' })],
    ['no overall rating', { imf_dsa: { ...IMF_DSA, overall_risk_of_debt_distress: '' } }],
    ['no external rating', { imf_dsa: { ...IMF_DSA, risk_of_external_debt_distress: undefined } }],
  ])('%s → null', (_label, payload) => {
    expect(readDsaRating(payload)).toBeNull();
  });

  it('returns a cited rating unchanged', () => {
    expect(readDsaRating({ imf_dsa: IMF_DSA })).toEqual(IMF_DSA);
  });
});

describe('the citation says where the rating is printed', () => {
  const r = readDsaRating({ imf_dsa: IMF_DSA })!;

  it('dates the link by the DSA, not by today', () => {
    expect(dsaSourceLabel(r)).toBe('IMF–World Bank DSA, Oct 2024');
  });

  it('shows the publication and confirmation dates without requiring hover', () => {
    expect(dsaVintageLabel(r)).toContain('Published 1 Nov 2024');
    expect(dsaVintageLabel(r)).toContain('31 Mar 2026');
    expect(dsaVintageLabel(r)).toContain('current status unverified');
  });

  it('opens the PDF at the rating page', () => {
    expect(dsaHref(r)).toBe(`${IMF_DSA.source.url}#page=132`);
  });

  it('names the report, the page, the date, and when it was last confirmed as the latest', () => {
    const c = dsaCitation(r);
    expect(c).toContain('Overall risk of debt distress: High');
    expect(c).toContain('risk of external debt distress: High');
    expect(c).toContain('IMF Country Report No. 24/316');
    expect(c).toContain('PDF p. 132');
    expect(c).toContain('18 Oct 2024');
    expect(c).toContain('31 Mar 2026');
  });

  it('does not let a timezone move the month', () => {
    // `new Date('2024-11-01')` is 31 Oct in UTC-anything. Parsing by hand
    // keeps the label on the date the IMF printed.
    const nov = readDsaRating(withSource({ dsa_date: '2024-11-01' }))!;
    expect(dsaSourceLabel(nov)).toBe('IMF–World Bank DSA, Nov 2024');
  });
});

describe('dsaIsAlarm', () => {
  it.each([
    ['High', true],
    ['In debt distress', true],
    ['Moderate', false],
    ['Low', false],
  ])('%s → %s', (overall, alarm) => {
    const r = readDsaRating({ imf_dsa: { ...IMF_DSA, overall_risk_of_debt_distress: overall } });
    expect(dsaIsAlarm(r)).toBe(alarm);
  });

  it('is never raised by an absent rating', () => {
    expect(dsaIsAlarm(null)).toBe(false);
  });
});
