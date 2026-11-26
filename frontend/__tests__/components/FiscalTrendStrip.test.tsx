import { render, screen } from '@testing-library/react';
import FiscalTrendStrip from '@/components/budget/FiscalTrendStrip';
import { historyChange, historyPeriods, observeHistory, type FiscalHistoryRow } from '@/components/budget/fiscalHistory';

function revenueRow(year: string, value: number, vintage: string): FiscalHistoryRow {
  return {
    fiscal_year: year,
    total_revenue: value,
    measure_qualifications: {
      total_revenue: {
        fiscal_year: year, value_kes: value * 1e9, vintage, basis: 'ordinary_revenue_excl_aia', precision_kes: 1e6,
        source: { title: 'Synthetic Treasury report', url: 'https://treasury.go.ke/synthetic-test.pdf', page: 12, sha256: 'a'.repeat(64), column: vintage },
      },
    },
  };
}

function revenueObservations(...rows: FiscalHistoryRow[]) {
  return historyPeriods(rows).map(period => observeHistory(period, 'total_revenue'));
}

it('keeps returned period slots, normalizes the label and withholds conflicting duplicate years', () => {
  const observations = revenueObservations(
    revenueRow('FY 2025/26', 40, 'Actual'),
    revenueRow('FY2023/24', 30, 'Actual'),
    revenueRow('2023/24', 31, 'Approved'),
    { fiscal_year: 'FY 2024/25' },
    revenueRow('FY 2026/29', 99, 'Approved'),
  );
  expect(observations.map(({ year, value, code }) => [year, value, code])).toEqual([
    ['2023/24', null, 'withheld'], ['2024/25', null, undefined], ['2025/26', 40, 'actual'],
  ]);
});

it('compares the most recent slot with the earliest supported value of the same basis and vintage', () => {
  const observations = revenueObservations(
    revenueRow('FY 2022/23', 50, 'Preliminary'),
    revenueRow('FY2023/24', 100, 'Approved'),
    revenueRow('FY 2024/25', 200, 'Actual'),
    revenueRow('FY 2025/26', 125, 'Approved'),
  );
  expect(historyChange(observations)).toEqual({ change: 0.25, start: '2023/24' });
});

it('omits a delta for missing, zero-baseline, mismatched or basis-unconfirmed comparisons', () => {
  const approved = revenueRow('FY2025/26', 125, 'Approved');
  const cases = [
    [revenueRow('FY2023/24', 0, 'Approved'), approved],
    [revenueRow('FY2023/24', 100, 'Preliminary'), approved],
    [{ fiscal_year: 'FY2023/24', total_revenue: 100 }, approved],
    [revenueRow('FY2023/24', 100, 'Approved'), { fiscal_year: 'FY2025/26' }],
  ];
  for (const rows of cases) expect(historyChange(revenueObservations(...rows))).toBeNull();
  expect(historyChange(revenueObservations(revenueRow('FY2023/24', 100, 'Approved'), revenueRow('FY2025/26', 0, 'Approved'))))
    .toEqual({ change: -1, start: '2023/24' });
});

it('withholds a figure when the proof has a different fiscal period, amount, accounting basis or visible column', () => {
  const row = revenueRow('FY2025/26', 125, 'Approved');
  const proof = row.measure_qualifications!.total_revenue;
  for (const overrides of [
    { fiscal_year: 'FY2024/25' }, { value_kes: 124e9 }, { basis: 'revenue_including_aia' },
    { source: { ...proof.source, column: 'Actual' } },
  ]) {
    const changed = { ...row, measure_qualifications: { total_revenue: { ...proof, ...overrides } } };
    expect(revenueObservations(changed)[0]).toEqual({ year: '2025/26', value: null, code: 'withheld' });
  }
});

it('retains the legacy caption and marks amounts unconfirmed, while a per-measure absence stays withheld', () => {
  render(<FiscalTrendStrip history={[
    { fiscal_year: 'FY2024/25', debt_service_cost: 32, debt_service_source: { title: 'Legacy debt report' } },
    { fiscal_year: 'FY2025/26', debt_service_cost: 99, absent_reasons: { debt_service_cost: 'measure_source_unconfirmed' } },
  ]} />);
  expect(screen.getByText('Legacy debt report')).toBeInTheDocument();
  expect(screen.getByText(/\? = Basis unconfirmed/)).toBeInTheDocument();
  expect(screen.getByText(/× = Withheld/)).toBeInTheDocument();
  expect(screen.queryByText('99B')).toBeNull();
});
