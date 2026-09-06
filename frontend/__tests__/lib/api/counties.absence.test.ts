/**
 * The counties adapter must not invent a zero for a figure the API withheld.
 *
 * `transformCountyData` used to end three fields in `|| 0` / `?? 0`:
 *
 *   const budget = bc.total_budget || bc.budget_2025 || 0;
 *   const debt   = bc.total_debt   || bc.debt        || 0;
 *   moneyReceived: bc.money_received ?? bc.total_spent ?? 0,
 *
 * which made "the API did not publish this figure" and "the figure is zero"
 * indistinguishable to every component downstream. A zero is a claim — that a
 * county was allocated nothing, owes nothing, or received nothing — and none of
 * those are things an absent field says.
 *
 * A zero arriving FROM the API is treated as absence too, deliberately: every
 * one of these fields is a SUM over rows on the backend (budget lines, loans),
 * so 0.0 is an empty aggregate, not a measured zero. No county is allocated
 * nothing — all 47 receive an equitable share by constitutional formula — so
 * "KES 0" there can only ever mean "nothing ingested".
 */
import { transformCountyData } from '@/lib/api/counties';

/** The minimum the backend always sends; figures are layered on per-test. */
const base = {
  id: 'baringo',
  name: 'Baringo',
  population: 666_763,
  budget_2025: 0,
  financial_health_score: 42.9,
  audit_rating: '',
  audit_status: 'pending',
};

describe('transformCountyData — absent figures stay absent', () => {
  it('leaves budget undefined when the API publishes no budget', () => {
    const c = transformCountyData({ ...base } as never);
    expect(c.budget).toBeUndefined();
    expect(c.totalBudget).toBeUndefined();
  });

  it('leaves debt undefined when the API publishes no debt', () => {
    const c = transformCountyData({ ...base } as never);
    expect(c.debt).toBeUndefined();
    expect(c.totalDebt).toBeUndefined();
  });

  it('leaves moneyReceived undefined when the API publishes no transfers', () => {
    const c = transformCountyData({ ...base } as never);
    expect(c.moneyReceived).toBeUndefined();
  });

  it('treats an explicit zero as absence, not as a figure', () => {
    const c = transformCountyData({
      ...base,
      total_budget: 0,
      total_debt: 0,
      money_received: 0,
      total_spent: 0,
    } as never);
    expect(c.budget).toBeUndefined();
    expect(c.debt).toBeUndefined();
    expect(c.moneyReceived).toBeUndefined();
  });

  it('still carries published figures through unchanged', () => {
    const c = transformCountyData({
      ...base,
      budget_2025: 9_542_030_000,
      total_budget: 9_542_030_000,
      total_debt: 450_065_025,
      money_received: 9_542_030_000,
    } as never);
    expect(c.budget).toBe(9_542_030_000);
    expect(c.totalBudget).toBe(9_542_030_000);
    expect(c.debt).toBe(450_065_025);
    expect(c.totalDebt).toBe(450_065_025);
    expect(c.moneyReceived).toBe(9_542_030_000);
  });

  it('falls back to the alternate key when the preferred one is absent', () => {
    const c = transformCountyData({
      ...base,
      budget_2025: 9_542_030_000,
      debt: 450_065_025,
      total_spent: 4_093_530_870,
    } as never);
    expect(c.budget).toBe(9_542_030_000);
    expect(c.debt).toBe(450_065_025);
    expect(c.moneyReceived).toBe(4_093_530_870);
  });

  it('does not let a null from the API become a zero', () => {
    const c = transformCountyData({
      ...base,
      total_budget: null,
      total_debt: null,
      money_received: null,
      total_spent: null,
    } as never);
    expect(c.budget).toBeUndefined();
    expect(c.debt).toBeUndefined();
    expect(c.moneyReceived).toBeUndefined();
  });

  it('rejects a non-finite figure rather than publishing NaN', () => {
    const c = transformCountyData({
      ...base,
      total_budget: Number.NaN,
      total_debt: Number.POSITIVE_INFINITY,
    } as never);
    expect(c.budget).toBeUndefined();
    expect(c.debt).toBeUndefined();
  });
});

describe('pendingBills: not reported is not zero', () => {
  // Narok submitted no pending-bills data to the Treasury for FY 2024/25.
  // The BROP prints an empty row for it and says so in a footnote, so the API
  // returns null. `?? 0` used to turn that into "KSh 0 pending bills", which
  // is a claim the county owes nothing — one nobody has made.
  it('renders absence, not zero, when the API reports none', () => {
    const county = transformCountyData({
      id: 'narok',
      name: 'Narok',
      pending_bills: null,
    } as never);

    expect(county.pendingBills).toBeUndefined();
    expect(county.pendingBills).not.toBe(0);
  });

  it('keeps a genuine published zero', () => {
    // A publisher CAN report zero pending bills, and that is a figure. This
    // is why the field does not go through publishedAmount(), which drops
    // zeros because its own fields are backend SUMs.
    const county = transformCountyData({
      id: 'x',
      name: 'X',
      pending_bills: 0,
    } as never);

    expect(county.pendingBills).toBe(0);
  });

  it('passes a reported figure through', () => {
    const county = transformCountyData({
      id: 'nairobi',
      name: 'Nairobi',
      pending_bills: 86_769_200_000,
    } as never);

    expect(county.pendingBills).toBe(86_769_200_000);
  });
});

describe('fiscal grade: no score means no grade', () => {
  // The financial-health index returns null when fewer than two of its
  // components can be computed. `bc.financial_health_score || 0` graded such
  // a county a "C" — the lowest grade, awarded for having no data.
  it('does not grade a county the API could not score', () => {
    const county = transformCountyData({
      id: 'x',
      name: 'X',
      financial_health_score: null,
    } as never);

    expect(county.financial_health_score).toBeUndefined();
    expect(county.fiscal_grade).toBeUndefined();
  });

  it('does not turn an absent score into zero', () => {
    const county = transformCountyData({ id: 'x', name: 'X' } as never);

    expect(county.financial_health_score).not.toBe(0);
    expect(county.fiscal_grade).not.toBe('C');
  });

  it('grades a county that has a score', () => {
    const county = transformCountyData({
      id: 'y',
      name: 'Y',
      financial_health_score: 59.6,
    } as never);

    expect(county.financial_health_score).toBe(59.6);
    expect(county.fiscal_grade).toBe('B');
  });

  it('keeps a genuine zero score, which is a measurement', () => {
    const county = transformCountyData({
      id: 'z',
      name: 'Z',
      financial_health_score: 0,
    } as never);

    expect(county.financial_health_score).toBe(0);
    expect(county.fiscal_grade).toBe('C');
  });
});
