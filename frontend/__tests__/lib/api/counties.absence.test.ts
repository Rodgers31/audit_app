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
