import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import React from 'react';
import type { FigureQualification } from '@/lib/evidence/qualification';
import type { County } from '@/types';

const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockCounty = (overrides: Partial<County>): County =>
  ({
    id: '005',
    name: 'Lamu',
    code: '005',
    population: 143920,
    budget: 5.6e9,
    totalBudget: 5.6e9,
    debt: null,
    totalDebt: null,
    budgetUtilization: 76,
    financial_health_score: 75,
    audit_rating: '',
    auditStatus: 'pending',
    ...overrides,
  }) as County;
const currentYear = 'FY2025/26';
const partialYear = 'FY2025/26 9M';

function sourcedCounty(county: County, period: string): County {
  const amount = (measure: string): FigureQualification => ({
    status: 'qualified',
    reason: 'historical_source_not_value_checked',
    source_kind: 'pdf',
    source_document_id: 20,
    publisher: 'Controller of Budget',
    source_url: 'https://cob.go.ke/fixture.pdf',
    receipt_id: null,
    digest: null,
    locator: null,
    document_bytes_checked: false,
    value_checked: false,
    identity: {
      measure,
      entity_id: Number(county.id),
      geography: `${county.name} County`,
      period,
      unit: 'KES',
      basis: 'actual',
      dimensions: { category: 'Total' },
    },
  });
  return {
    ...county,
    budgetSource: 'cob_cbirr',
    figureQualifications: {
      budget_lines: { '20': { allocated_amount: amount('allocated_amount'), actual_spent: amount('actual_spent') } },
    },
  };
}

const mockCurrent = [
  sourcedCounty(mockCounty({}), currentYear),
  mockCounty({ id: '002', name: 'Kwale', code: '002', budgetUtilization: 99 }),
  sourcedCounty(mockCounty({ id: '001', name: 'Mombasa', code: '001', budgetUtilization: 0 }), currentYear),
];
const mockEarlier = [
  sourcedCounty(mockCounty({ budgetUtilization: 38, financial_health_score: 60 }), partialYear),
  mockCurrent[1],
  mockCurrent[2],
];
const mockYears = {
  years: [
    { label: 'FY2025/26', source: 'cob_cbirr', counties: 2 },
    { label: 'FY2025/26 9M', source: 'cob_cbirr', counties: 2 },
  ],
  default: 'FY2025/26',
};

jest.mock('next/navigation', () => ({
  usePathname: () => '/counties',
  useRouter: () => ({ replace: mockReplace, push: mockPush }),
  useSearchParams: () => new URLSearchParams(''),
}));
jest.mock('@/lib/react-query', () => ({
  // Cached data returns immediately: no loading-state unmount may reset
  // inspection and conceal the stale object from the previous fiscal year.
  useCounties: ({ fiscalYear }: { fiscalYear?: string }) => ({
    data: fiscalYear === 'FY2025/26 9M' ? mockEarlier : mockCurrent,
    isLoading: false,
    error: null,
    refetch: jest.fn(),
  }),
  useCountyFiscalYears: () => ({ data: mockYears, isLoading: false, error: null }),
}));
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));

import CountiesPageClient from '@/app/counties/CountiesPageClient';

function renderExplorer() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<CountiesPageClient />, {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
}

const readout = () => document.querySelector('[class*=mapReadout]') as HTMLElement;
const lamuPolygon = () => screen.getByRole('link', { name: /^Lamu, Spending rate/ });

function openMap() {
  renderExplorer();
  fireEvent.click(screen.getByRole('button', { name: 'Map' }));
}

beforeEach(() => {
  mockPush.mockClear();
  mockReplace.mockClear();
  window.history.replaceState(null, '', '/counties');
});

describe('County map persistent readout', () => {
  it('opens on a spending-ranked list and carries the same qualified rates to the map', () => {
    renderExplorer();
    expect(screen.getByRole('button', { name: 'List' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('region', { name: 'County spending map' })).not.toBeInTheDocument();
    const table = screen.getByRole('table', { name: 'County Rankings' });
    const rows = () => Array.from(table.querySelectorAll('tbody tr'));
    expect(rows().map((row) => (row.children[0].textContent ?? '') + row.children[1].textContent)).toEqual(['1Lamu', '2Mombasa', '—Kwale']);
    expect(rows()[0]).toHaveTextContent('76.0%On target');
    expect(rows()[1]).toHaveTextContent('0.0%Well below target');
    expect(rows()[2]).toHaveTextContent('No published rate');
    fireEvent.click(screen.getByRole('columnheader', { name: /Spending rate/ }));
    expect(rows().map((row) => (row.children[0].textContent ?? '') + row.children[1].textContent)).toEqual(['1Mombasa', '2Lamu', '—Kwale']);

    fireEvent.click(screen.getByRole('button', { name: 'Map' }));
    const map = screen.getByRole('region', { name: 'County spending map' });
    expect(within(map).getByRole('link', { name: 'Lamu, Spending rate, 76.0%, On target' }))
      .toHaveAttribute('data-spending-band', 'on');
    expect(within(map).getByRole('link', { name: 'Mombasa, Spending rate, 0.0%, Well below target' }))
      .toHaveAttribute('data-spending-band', 'well-below');
    expect(within(map).getByRole('link', { name: 'Kwale, Spending rate, No published rate' }))
      .toHaveAttribute('data-spending-band', 'unavailable');
    expect(screen.queryByRole('table', { name: 'County Rankings' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'List' }));
    expect(rows().map((row) => (row.children[0].textContent ?? '') + row.children[1].textContent)).toEqual(['1Mombasa', '2Lamu', '—Kwale']);
  });

  it('reads the inspected county from the current cached reporting period', () => {
    openMap();
    fireEvent.focus(lamuPolygon());
    expect(readout()).toHaveTextContent('76.0%');
    fireEvent.change(screen.getByRole('combobox', { name: 'Year' }), {
      target: { value: 'FY2025/26 9M' },
    });
    expect(readout()).toHaveTextContent('38.0% Reported for this period');
    expect(lamuPolygon()).toHaveAttribute('data-spending-band', 'reported');
    expect(screen.queryByText('Annual target: 70%')).not.toBeInTheDocument();
    expect(readout()).not.toHaveTextContent('76.0%');
    expect(within(readout()).getByRole('link', { name: /Lamu/ })).toHaveAttribute(
      'href',
      '/counties/005?fy=FY2025%2F26%209M'
    );
  });

  it('resets inspection to a matching county when the prior county is filtered out', () => {
    openMap();
    fireEvent.focus(lamuPolygon());
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'Mombasa' },
    });
    expect(within(readout()).getByRole('link', { name: /Mombasa/ })).toBeInTheDocument();
    expect(within(readout()).queryByRole('link', { name: /Lamu/ })).not.toBeInTheDocument();
  });

  it('keeps excluded county geometry as context without offering it as a map link', () => {
    openMap();
    const excluded = lamuPolygon();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'Mombasa' },
    });

    expect(excluded).toBeInTheDocument();
    expect(excluded).not.toHaveAttribute('role', 'link');
    expect(excluded).not.toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('link', { name: /^Mombasa, Spending rate/ })).toHaveAttribute('tabindex', '0');
  });

  it.each(['click', 'Enter'] as const)(
    'does not navigate an excluded county through %s',
    (interaction) => {
      openMap();
      const excluded = lamuPolygon();
      fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
        target: { value: 'Mombasa' },
      });

      if (interaction === 'click') fireEvent.click(excluded);
      else fireEvent.keyDown(excluded, { key: 'Enter' });

      expect(mockPush).not.toHaveBeenCalled();
      expect(within(readout()).getByRole('link', { name: /Mombasa/ })).toBeInTheDocument();
    }
  );

  it.each(['focus', 'mouseEnter'] as const)(
    'does not inspect an excluded county through %s and reveal it after clearing filters',
    (interaction) => {
      openMap();
      const excluded = lamuPolygon();
      fireEvent.focus(screen.getByRole('link', { name: /^Mombasa, Spending rate/ }));
      fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
        target: { value: 'Mombasa' },
      });

      fireEvent[interaction](excluded);
      fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
        target: { value: '' },
      });

      expect(within(readout()).getByRole('link', { name: /Mombasa/ })).toBeInTheDocument();
      expect(within(readout()).queryByRole('link', { name: /Lamu/ })).not.toBeInTheDocument();
    }
  );

  it('offers no county navigation when filters match no county', () => {
    openMap();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'No matching county' },
    });

    const map = screen.getByRole('region', { name: 'County spending map' });
    expect(within(map).queryAllByRole('link')).toHaveLength(0);
  });

  it('navigates a focused map polygon with Enter and retains the selected year', () => {
    openMap();
    fireEvent.change(screen.getByRole('combobox', { name: 'Year' }), {
      target: { value: 'FY2025/26 9M' },
    });
    fireEvent.keyDown(lamuPolygon(), { key: 'Enter' });
    expect(mockPush).toHaveBeenCalledWith('/counties/005?fy=FY2025%2F26%209M');
  });
});
