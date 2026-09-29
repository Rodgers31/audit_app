import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import React from 'react';
import CountiesPageClient from '@/app/counties/CountiesPageClient';
import type { County } from '@/types';
import { financialHealthBand } from '@/lib/counties/financialHealth';
import { getCountyRegion, normalizeCountyName } from '@/lib/counties/regions';

const county = (name: string, score: number | null, id: string): County =>
  ({
    id,
    code: id,
    name,
    population: null,
    budget: 1e9,
    totalBudget: 1e9,
    debt: null,
    totalDebt: null,
    budgetUtilization: null,
    financial_health_score: score,
    audit_rating: '',
    auditStatus: 'pending',
  }) as unknown as County;

let mockCounties: County[] = [];
jest.mock('next/navigation', () => ({
  usePathname: () => '/counties',
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
jest.mock('@/lib/react-query', () => ({
  useCounties: () => ({ data: mockCounties, isLoading: false, error: null, refetch: jest.fn() }),
  useCountyFiscalYears: () => ({
    data: { years: [{ label: 'FY2025/26', source: 'cob_cbirr', counties: 47 }], default: 'FY2025/26' },
    isLoading: false,
    error: null,
  }),
}));
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));

beforeEach(() => {
  mockCounties = [];
  window.history.replaceState(null, '', '/counties');
});

it('uses the ranking letter for map fills, legend filters, and the regional average', () => {
  mockCounties = [
    county('Lamu', 76, '005'),
    county('Taita Taveta', 45, '006'),
    county('Mombasa', null, '047'),
  ];
  render(<CountiesPageClient />);
  const map = screen.getByRole('region', { name: 'County Performance Map' });
  const lamu = within(map).getByRole('link', { name: 'Lamu, Grade: B+' });
  const taita = within(map).getByRole('link', { name: 'Taita Taveta, Grade: B-' });
  const bPlus = within(map).getByRole('button', { name: 'B+' });
  const bMinus = within(map).getByRole('button', { name: 'B-' });
  expect(lamu).toHaveAttribute('fill', bPlus.style.getPropertyValue('--grade-color'));
  expect(taita).toHaveAttribute('fill', bMinus.style.getPropertyValue('--grade-color'));
  expect(screen.getByText('B (60.5)')).toBeInTheDocument();

  fireEvent.click(bPlus);
  expect(within(map).getByRole('link', { name: 'Lamu, Grade: B+' })).toBeInTheDocument();
  expect(taita).not.toHaveAttribute('role', 'link');
  expect(screen.getByText('B+ (76.0)')).toBeInTheDocument();
});

it('keeps missing and non-finite health scores ungraded on the map and ranking', () => {
  mockCounties = [county('Lamu', null, '005'), county('Mombasa', Number.NaN, '047')];
  render(<CountiesPageClient />);
  const map = screen.getByRole('region', { name: 'County Performance Map' });
  expect(within(map).getByRole('link', { name: 'Lamu, Grade: —' })).toHaveAttribute('fill', '#b8bcb2');
  expect(within(map).getByRole('link', { name: 'Mombasa, Grade: —' })).toHaveAttribute('fill', '#b8bcb2');
  expect(screen.queryByText(/Unknown \(/)).not.toBeInTheDocument();
});

it('offers B+ and B- in the sidebar and filters by the same health band as the map', () => {
  mockCounties = [county('Lamu', 76, '005'), county('Taita Taveta', 45, '006')];
  render(<CountiesPageClient />);
  fireEvent.click(screen.getByRole('button', { name: 'Filters' }));
  const gradeChoices = screen.getByRole('group', { name: 'Grade' });
  expect(within(gradeChoices).getByRole('button', { name: 'B+' })).toBeInTheDocument();
  fireEvent.click(within(gradeChoices).getByRole('button', { name: 'B-' }));
  expect(screen.getByText('1 County')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: 'County Performance Map' }))
    .getByRole('link', { name: 'Taita Taveta, Grade: B-' })).toBeInTheDocument();
});

it('ranks a reported health score before unavailable scores in both directions', () => {
  mockCounties = [
    county('Lamu', null, '005'),
    county('Mombasa', 76, '047'),
    county('Kwale', Number.NaN, '002'),
  ];
  render(<CountiesPageClient />);
  const names = () => Array.from(screen.getByRole('table').querySelectorAll('tbody tr')).map(
    (row) => row.querySelector('td:nth-child(2) a span:last-child')?.textContent?.trim()
  );
  const health = screen.getByRole('columnheader', { name: /Health/ });
  fireEvent.click(health);
  expect(names()[0]).toBe('Mombasa');
  fireEvent.click(health);
  expect(names()[0]).toBe('Mombasa');
});

it('does not call an ungraded county a worst health performer', () => {
  mockCounties = [
    county('Lamu', 76, '005'), county('Kwale', 45, '002'), county('Mombasa', null, '047'),
  ];
  render(<CountiesPageClient />);
  const needsAttention = screen.getByRole('heading', { name: 'Needs Attention' }).parentElement!;
  expect(needsAttention).toHaveTextContent('Kwale');
  expect(needsAttention).not.toHaveTextContent('Mombasa');
});

it('shows an unavailable state when no county has a health score', () => {
  mockCounties = [county('Lamu', null, '005'), county('Mombasa', Number.NaN, '047')];
  render(<CountiesPageClient />);
  expect(screen.getByText('No financial-health grades are available for this selection.')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Needs Attention' })).not.toBeInTheDocument();
});

it('classifies the same rounded average health score the reader sees', () => {
  mockCounties = [county('Lamu', 84.9, '005'), county('Mombasa', 85, '047')];
  render(<CountiesPageClient />);
  expect(screen.getByText('A (85.0)')).toBeInTheDocument();
});

const REGIONS: Record<string, string[]> = {
  central: ['Nyandarua', 'Nyeri', 'Kirinyaga', "Murang'a", 'Kiambu'],
  coast: ['Kwale', 'Kilifi', 'Tana River', 'Lamu', 'Taita Taveta', 'Mombasa'],
  eastern: ['Marsabit', 'Isiolo', 'Meru', 'Tharaka Nithi', 'Embu', 'Kitui', 'Machakos', 'Makueni'],
  nairobi: ['Nairobi'],
  'north-eastern': ['Garissa', 'Wajir', 'Mandera'],
  nyanza: ['Siaya', 'Kisumu', 'Homa Bay', 'Migori', 'Kisii', 'Nyamira'],
  'rift-valley': [
    'Turkana', 'West Pokot', 'Samburu', 'Trans Nzoia', 'Uasin Gishu', 'Elgeyo Marakwet',
    'Nandi', 'Baringo', 'Laikipia', 'Nakuru', 'Narok', 'Kajiado', 'Kericho', 'Bomet',
  ],
  western: ['Kakamega', 'Vihiga', 'Bungoma', 'Busia'],
};

it('places all 47 API county names in exactly one intended region and includes valid aliases', () => {
  const names = Object.values(REGIONS).flat();
  expect(names).toHaveLength(47);
  expect(new Set(names).size).toBe(47);
  expect(new Set(names.map(normalizeCountyName)).size).toBe(47);
  mockCounties = names.map((name, index) => county(name, 60, String(index + 1).padStart(3, '0')));
  render(<CountiesPageClient />);
  const region = screen.getByRole('combobox', { name: 'Region' });
  const rows = () => Array.from(screen.getByRole('table').querySelectorAll('tbody tr'));
  for (const [slug, expectedNames] of Object.entries(REGIONS)) {
    fireEvent.change(region, { target: { value: slug } });
    expect(screen.getByText(`${expectedNames.length} ${expectedNames.length === 1 ? 'County' : 'counties'}`)).toBeInTheDocument();
    for (const name of expectedNames) {
      expect(getCountyRegion(name)).toBe(slug);
      if (expectedNames.length <= 10) {
        expect(rows().some((row) => row.textContent?.includes(name))).toBe(true);
      }
    }
    if (slug === 'coast') {
      expect(within(screen.getByRole('region', { name: 'County Performance Map' }))
        .getByRole('link', { name: 'Taita Taveta, Grade: B' })).toBeInTheDocument();
    }
  }
});

it.each([
  [0, 'C'], [39.9, 'C'], [40, 'B-'], [54.9, 'B-'], [55, 'B'],
  [69.9, 'B'], [70, 'B+'], [76, 'B+'], [84.9, 'B+'], [85, 'A'], [100, 'A'],
] as const)('grades %s as %s at a health-band boundary', (score, expected) => {
  expect(financialHealthBand(score)?.grade).toBe(expected);
});

it.each([null, undefined, Number.NaN, Infinity, -1, 101])(
  'does not grade an unavailable or invalid score %s',
  (score) => expect(financialHealthBand(score)).toBeNull()
);

it.each([
  ['Taita Taveta', 'Taita-Taveta County', 'coast'],
  ['Trans Nzoia', 'Trans-Nzoia County', 'rift-valley'],
  ['Tharaka Nithi', 'Tharaka-Nithi County', 'eastern'],
  ['Elgeyo Marakwet', 'Elgeyo-Marakwet County', 'rift-valley'],
  ['Homa Bay', 'HomaBay', 'nyanza'],
  ['Nairobi', 'Nairobi City County', 'nairobi'],
] as const)('matches %s and its map/alias spelling', (apiName, alias, region) => {
  if (apiName !== 'Nairobi') {
    expect(normalizeCountyName(apiName)).toBe(normalizeCountyName(alias));
  }
  expect(getCountyRegion(apiName)).toBe(region);
  expect(getCountyRegion(alias)).toBe(region);
});

it('leaves an unrecognized county outside every region', () => {
  expect(getCountyRegion('Unrecognized County')).toBeNull();
});
