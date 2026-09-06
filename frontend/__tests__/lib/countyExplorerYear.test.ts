/**
 * The county explorer's year must come from the data, not the calendar.
 *
 * `CountiesPageClient` seeded its dropdown with `getLatestReportedFiscalYear()`,
 * which is computed from `new Date()`:
 *
 *   const startYear = now.getMonth() >= 6 ? now.getFullYear() - 1 : now.getFullYear() - 2;
 *
 * In September 2026 that is "2025/26" — the CRA equitable-share projection. So
 * the explorer requested `GET /counties?fiscal_year=2025/26` and published
 * Baringo at KES 7.13B, while the county's own page sends no year, lets the API
 * resolve the period from the rows that exist, and published KES 9.54B from the
 * Controller of Budget's CBIRR. Same county, same site, two budgets.
 *
 * `GET /api/v1/counties/fiscal-years` now reports the years county budget data
 * exists for and which one the API resolves to by default — resolved by the
 * same rule `GET /counties` applies when given no year, so the label and the
 * figures cannot describe different periods.
 */
import {
  moneyFlowDefaultYear,
  resolveExplorerYear,
  serviceableFiscalYear,
  transparencyYearOptions,
} from '@/lib/utils';

/**
 * What the removed calendar helpers returned on the frozen date below. They
 * are literals now because the helpers are gone — `getLatestReportedFiscalYear`,
 * `generateFiscalYears` and `getCurrentFiscalYear` were all deleted from
 * `@/lib/utils` — but the numbers are why: each is a year the database held no
 * reported figures for, and each is what a page was showing before these
 * resolvers replaced them.
 *
 * The one surviving caller of a clock-derived fiscal year — the pulsing
 * "still running" dot on /transparency — keeps its own local, unexported
 * helper, so there is no shared one left to reach for when the question is
 * about data rather than the calendar.
 */
const CALENDAR_ON_2026_09 = {
  /** getLatestReportedFiscalYear() — the CRA projection period. */
  latestReported: '2025/26',
  /** getCurrentFiscalYear(), and generateFiscalYears()[0] — a year in no list at all. */
  newestGenerated: '2026/27',
};

/** The live payload on 2026-09-05, abridged. */
const META = {
  years: [
    { label: 'FY2025/26', source: 'cra_model' as const, counties: 47 },
    { label: 'FY2024/25', source: 'cob_cbirr' as const, counties: 47 },
    { label: 'FY2023/24', source: 'cra_model' as const, counties: 47 },
  ],
  default: 'FY2024/25',
};

describe('resolveExplorerYear', () => {
  afterEach(() => jest.useRealTimers());

  it('takes the API default, not the year the calendar is in', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-09-05T00:00:00Z'));
    // The old seed produced the in-progress, unreported FY on this date.
    // What the data says has actually been reported is a different year:
    expect(resolveExplorerYear(undefined, META)).toBe('FY2024/25');
    expect(resolveExplorerYear(undefined, META)).not.toBe(
      `FY${CALENDAR_ON_2026_09.latestReported}`
    );
  });

  it('is stable across the calendar', () => {
    // The old seed changed answer every 1 July regardless of whether a new
    // report had landed. This one only moves when the data moves.
    for (const day of ['2026-06-30', '2026-07-01', '2027-01-15']) {
      jest.useFakeTimers().setSystemTime(new Date(`${day}T00:00:00Z`));
      expect(resolveExplorerYear(undefined, META)).toBe('FY2024/25');
    }
  });

  it("keeps the reader's own choice", () => {
    expect(resolveExplorerYear('FY2025/26', META)).toBe('FY2025/26');
  });

  it('reports no year when the API offers none', () => {
    // Absence stays absence. Falling back to a calendar label here would put
    // a year on screen that nothing in the database supports.
    expect(resolveExplorerYear(undefined, { years: [], default: null })).toBeUndefined();
    expect(resolveExplorerYear(undefined, undefined)).toBeUndefined();
  });

  it('ignores a stored choice the API no longer offers', () => {
    // A bookmarked ?fy= for a year that has since been dropped must not be
    // sent back to the API, which would resolve it to nothing (or, worse,
    // fall through to an unfiltered query).
    expect(resolveExplorerYear('FY2019/20', META)).toBe('FY2024/25');
  });
});

/**
 * The API now refuses a fiscal_year it holds no county budget data for (404)
 * instead of silently answering with another period's figures. A county page
 * reached with a stale `?fy=` bookmark would then render "Failed to load
 * county data" — which is wrong twice over: the county loads fine, and only
 * the requested year is unavailable.
 */
describe('serviceableFiscalYear', () => {
  it('passes through a year the API offers', () => {
    expect(serviceableFiscalYear('FY2023/24', META)).toBe('FY2023/24');
  });

  it('drops a year the API would refuse', () => {
    // The API resolves the period itself, and the page labels the year it
    // shows — so this is a dropped request, not a substituted figure.
    expect(serviceableFiscalYear('FY2019/20', META)).toBeUndefined();
    expect(serviceableFiscalYear('banana', META)).toBeUndefined();
  });

  it('sends nothing when no year was requested', () => {
    expect(serviceableFiscalYear(undefined, META)).toBeUndefined();
  });

  it('does not drop anything before the year list has arrived', () => {
    // Dropping on an unloaded list would cost every county page a second
    // fetch on the common path. Unknown is not the same as refused.
    expect(serviceableFiscalYear('FY2023/24', undefined)).toBe('FY2023/24');
    expect(serviceableFiscalYear('FY2019/20', undefined)).toBe('FY2019/20');
  });
});

/**
 * The Follow the Money tab picked its year with the same calendar helper,
 * matched against /audits/fiscal-years — every fiscal period, not the ones
 * county budget data exists for. In September 2026 it landed on FY2025/26, the
 * CRA projection.
 *
 * Worse, it chose independently of the page it sits on: the Budget & Debt tab
 * two clicks away could be showing FY2024/25 while this one showed FY2025/26,
 * for the same county, with no indication they differed.
 */
describe('moneyFlowDefaultYear', () => {
  afterEach(() => jest.useRealTimers());

  it('follows the year the rest of the county page is showing', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-09-05T00:00:00Z'));
    // The page resolved FY2024/25; the calendar would have said 2025/26.
    expect(moneyFlowDefaultYear(undefined, 'FY2024/25', META)).toBe('FY2024/25');
    expect(moneyFlowDefaultYear(undefined, 'FY2024/25', META)).not.toBe(
      `FY${CALENDAR_ON_2026_09.latestReported}`
    );
  });

  it('follows the page even onto a projection year', () => {
    // A reader who pinned ?fy=FY2025/26 sees that year on every tab. The tab
    // agreeing with its page matters more than which year the page picked.
    expect(moneyFlowDefaultYear(undefined, 'FY2025/26', META)).toBe('FY2025/26');
  });

  it("keeps the reader's own selection over the page's year", () => {
    expect(moneyFlowDefaultYear('FY2023/24', 'FY2024/25', META)).toBe('FY2023/24');
  });

  it('falls back to the API default when the page names no year', () => {
    expect(moneyFlowDefaultYear(undefined, undefined, META)).toBe('FY2024/25');
  });

  it('ignores a page year the API does not offer', () => {
    expect(moneyFlowDefaultYear(undefined, 'FY2019/20', META)).toBe('FY2024/25');
  });

  it('reports no year when the API offers none', () => {
    expect(
      moneyFlowDefaultYear(undefined, 'FY2024/25', { years: [], default: null })
    ).toBeUndefined();
  });
});

/**
 * The national Follow the Money page (/transparency) took its years from
 * /audits/fiscal-years — every FiscalPeriod row — and its default from a
 * wall-clock "current FY".
 *
 * On 2026-09-06 that current FY was 2026/27, which is in no list at all, so
 * the page fired two money-flow requests for a year with nothing behind it,
 * then corrected to years[0] = FY2025/26: the CRA projection (405,100m)
 * rather than the CBIRR-reported FY2024/25 (633,304m).
 *
 * Four of the eight pills it offered — FY2025/26 9M, FY2025/26 H1, FY2021/22,
 * FY2020/21 — are periods with no county budget rows, so clicking them
 * emptied the page.
 */
const TRANSPARENCY_META = {
  years: [
    { label: 'FY2025/26', source: 'cra_model' as const, counties: 47 },
    { label: 'FY2024/25', source: 'cob_cbirr' as const, counties: 47 },
    { label: 'FY2023/24', source: 'cra_model' as const, counties: 47 },
    { label: 'FY2022/23', source: 'cra_model' as const, counties: 47 },
  ],
  default: 'FY2024/25',
};

describe('transparencyYearOptions', () => {
  afterEach(() => jest.useRealTimers());

  it('defaults to the reported year, not the one the calendar is in', () => {
    jest.useFakeTimers().setSystemTime(new Date('2026-09-06T00:00:00Z'));
    const { years, default: def } = transparencyYearOptions(TRANSPARENCY_META);
    expect(def).toBe('2024/25');
    // Neither of the two labels the page used to reach for on this date.
    expect(def).not.toBe(CALENDAR_ON_2026_09.latestReported);
    expect(def).not.toBe(CALENDAR_ON_2026_09.newestGenerated);
    // ...and the second was not even offered, which is how the page ended up
    // fetching a year absent from its own picker (F37).
    expect(years).not.toContain(CALENDAR_ON_2026_09.newestGenerated);
  });

  it('offers only years with county budget data behind them', () => {
    const { years } = transparencyYearOptions(TRANSPARENCY_META);
    expect(years).toEqual(['2025/26', '2024/25', '2023/24', '2022/23']);
    // Periods that exist but carry no county rows must not be offered.
    expect(years).not.toContain('2025/26 9M');
    expect(years).not.toContain('2021/22');
  });

  it('strips the FY prefix so the picker and the selection compare equal', () => {
    // A mismatched form is what left no pill highlighted on load (F37).
    for (const y of transparencyYearOptions(TRANSPARENCY_META).years) {
      expect(y).toMatch(/^\d{4}\/\d{2}$/);
    }
  });

  it('offers the default among the years', () => {
    const { years, default: def } = transparencyYearOptions(TRANSPARENCY_META);
    expect(def).toBeDefined();
    expect(years).toContain(def!);
  });

  it('reports nothing rather than guessing when the API says nothing', () => {
    expect(transparencyYearOptions(undefined)).toEqual({ years: [], default: undefined });
    expect(transparencyYearOptions({ years: [], default: null })).toEqual({
      years: [],
      default: undefined,
    });
  });
});
