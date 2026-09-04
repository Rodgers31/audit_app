/**
 * Aggregation and ordering over county figures that may be absent.
 *
 * `sumPublished` exists because `counties.reduce((s, c) => s + (c.debt ?? 0))`
 * produces a total that looks complete and is silently short — it quietly
 * omits every county whose figure was never ingested while presenting the
 * result as "total county debt".
 *
 * `compareByPublishedFigure` exists because the obvious comparator is wrong in
 * one direction. Returning +1 for "a is absent" and letting the caller negate
 * the result for a descending sort puts the absent county FIRST — which on the
 * county rankings table read as the largest budget in Kenya.
 */
import {
  compareByPublishedFigure,
  countyBudget,
  countyDebt,
  sumPublished,
} from '@/lib/countyFigures';
import { County } from '@/types';

const county = (name: string, over: Partial<County> = {}): County =>
  ({
    id: name.toLowerCase(),
    name,
    population: 1_000_000,
    budget_2025: 0,
    financial_health_score: 50,
    audit_rating: '',
    fiscal_grade: 'B',
    ...over,
  }) as County;

describe('countyBudget / countyDebt', () => {
  it('prefers the primary key and falls back to the total', () => {
    expect(countyBudget(county('A', { budget: 10, totalBudget: 99 }))).toBe(10);
    expect(countyBudget(county('A', { totalBudget: 99 }))).toBe(99);
    expect(countyDebt(county('A', { debt: 5, totalDebt: 77 }))).toBe(5);
    expect(countyDebt(county('A', { totalDebt: 77 }))).toBe(77);
  });

  it('is undefined when neither key carries a figure', () => {
    expect(countyBudget(county('A'))).toBeUndefined();
    expect(countyDebt(county('A'))).toBeUndefined();
  });
});

describe('sumPublished', () => {
  it('sums only the counties that published, and says how many did', () => {
    const s = sumPublished(
      [county('A', { budget: 10 }), county('B'), county('C', { budget: 30 })],
      countyBudget
    );
    expect(s).toEqual({ total: 40, reported: 2, of: 3 });
  });

  it('withholds the total entirely when nobody published', () => {
    const s = sumPublished([county('A'), county('B')], countyBudget);
    expect(s.total).toBeNull();
    expect(s.reported).toBe(0);
  });

  it('does not fold an absent county in as a zero', () => {
    const withAbsent = sumPublished([county('A', { debt: 100 }), county('B')], countyDebt);
    const withoutIt = sumPublished([county('A', { debt: 100 })], countyDebt);
    expect(withAbsent.total).toBe(withoutIt.total);
    // The difference is visible in the coverage, not hidden in the total.
    expect(withAbsent.of).toBe(2);
    expect(withoutIt.of).toBe(1);
  });
});

describe('compareByPublishedFigure', () => {
  const big = county('Big', { budget: 30 });
  const small = county('Small', { budget: 10 });
  const absent = county('Absent');

  it('orders ascending', () => {
    expect(compareByPublishedFigure(small, big, countyBudget, 'asc')).toBeLessThan(0);
  });

  it('orders descending', () => {
    expect(compareByPublishedFigure(big, small, countyBudget, 'desc')).toBeLessThan(0);
  });

  it('sinks an absent figure when sorting ascending', () => {
    expect(compareByPublishedFigure(absent, small, countyBudget, 'asc')).toBeGreaterThan(0);
    expect(compareByPublishedFigure(small, absent, countyBudget, 'asc')).toBeLessThan(0);
  });

  it('sinks an absent figure when sorting DESCENDING too', () => {
    // The regression: a comparator whose result the caller negates put the
    // absent county at the top of the descending budget ranking.
    expect(compareByPublishedFigure(absent, big, countyBudget, 'desc')).toBeGreaterThan(0);
    expect(compareByPublishedFigure(big, absent, countyBudget, 'desc')).toBeLessThan(0);
  });

  it('sorts a real list with the absent county last in both directions', () => {
    const order = (dir: 'asc' | 'desc') =>
      [absent, small, big]
        .slice()
        .sort((a, b) => compareByPublishedFigure(a, b, countyBudget, dir))
        .map((c) => c.name);

    expect(order('asc')).toEqual(['Small', 'Big', 'Absent']);
    expect(order('desc')).toEqual(['Big', 'Small', 'Absent']);
  });

  it('treats two absent counties as tied', () => {
    expect(compareByPublishedFigure(absent, county('Absent2'), countyBudget, 'desc')).toBe(0);
  });
});
