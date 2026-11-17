import {
  countyDistributionPoints,
  nationalDistributionGuide,
} from '@/components/transparency/moneyFlowPresentation';
import type { MoneyFlowData } from '@/types';

const year = '2025/26 9M';

function flow(county_id: number | null, percentage: number | null): MoneyFlowData {
  return {
    county_id, county_name: `County ${county_id}`, fiscal_year: `FY${year}`,
    budget_source: 'cob_cbirr', efficiency_score: percentage, total_waste_estimate: null,
    source_document_url: 'https://cob.go.ke/reports/synthetic.pdf',
    stages: [
      { stage: 'Allocated', label: 'Allocation', amount: 100 },
      { stage: 'Spent', label: 'Spending', amount: percentage },
    ],
  };
}

it('keeps exact, zero and unavailable same-period county shares distinct', () => {
  const withheld = flow(5, 80);
  withheld.stages[1].data_unavailable = true;
  const points = countyDistributionPoints([
    flow(1, 0), flow(2, 69.96), flow(3, null),
    { ...flow(4, 90), budget_source: 'cra_model' }, withheld,
    { ...flow(6, 80), fiscal_year: '2025/26' },
    flow(null, 80),
  ], year);
  expect(points.map(({ id, percentage }) => [id, percentage])).toEqual([
    ['1', 0], ['2', 69.96], ['3', null], ['4', null], ['5', null],
  ]);
});

it('publishes one point per county', () => {
  const reported = flow(1, 70);
  expect(countyDistributionPoints([reported, reported], year)).toHaveLength(1);
});

it('uses a national guide only for the same period and a compatible published report', () => {
  const national = flow(null, 77);
  expect(nationalDistributionGuide(national, year)).toBe(77);
  expect(nationalDistributionGuide(national, '2025/26')).toBeNull();
  expect(nationalDistributionGuide({ ...national, source_document_url: null }, year)).toBeNull();
  expect(nationalDistributionGuide({ ...national, budget_source: 'mixed' }, year)).toBeNull();
  expect(nationalDistributionGuide(flow(null, 0), year)).toBe(0);
  expect(nationalDistributionGuide(flow(null, null), year)).toBeNull();
});
