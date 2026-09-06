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
  getLatestReportedFiscalYear,
  resolveExplorerYear,
  serviceableFiscalYear,
} from '@/lib/utils';

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
    // What the old seed produced — the in-progress, unreported FY.
    expect(getLatestReportedFiscalYear()).toBe('2025/26');
    // What the data says has actually been reported.
    expect(resolveExplorerYear(undefined, META)).toBe('FY2024/25');
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
