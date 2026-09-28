import '@testing-library/jest-dom';
import { fireEvent, render, screen, within } from '@testing-library/react';
import React from 'react';
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
const mockCurrent = [
  mockCounty({}),
  mockCounty({ id: '001', name: 'Mombasa', code: '001', budget: 18e9, totalBudget: 18e9 }),
];
const mockEarlier = [
  mockCounty({ budgetUtilization: 38, financial_health_score: 60 }),
  mockCurrent[1],
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

const readout = () => document.querySelector('[class*=mapReadout]') as HTMLElement;
const lamuPolygon = () => screen.getByRole('link', { name: /^Lamu, Grade:/ });

beforeEach(() => {
  mockPush.mockClear();
  mockReplace.mockClear();
  window.history.replaceState(null, '', '/counties');
});

describe('County map persistent readout', () => {
  it('reads the inspected county from the current cached reporting period', () => {
    render(<CountiesPageClient />);
    fireEvent.focus(lamuPolygon());
    expect(readout()).toHaveTextContent('76%');
    fireEvent.change(screen.getByRole('combobox', { name: 'Year' }), {
      target: { value: 'FY2025/26 9M' },
    });
    expect(readout()).toHaveTextContent('38%');
    expect(readout()).not.toHaveTextContent('76%');
    expect(within(readout()).getByRole('link', { name: /Lamu/ })).toHaveAttribute(
      'href',
      '/counties/005?fy=FY2025%2F26%209M'
    );
  });

  it('resets inspection to a matching county when the prior county is filtered out', () => {
    render(<CountiesPageClient />);
    fireEvent.focus(lamuPolygon());
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'Mombasa' },
    });
    expect(within(readout()).getByRole('link', { name: /Mombasa/ })).toBeInTheDocument();
    expect(within(readout()).queryByRole('link', { name: /Lamu/ })).not.toBeInTheDocument();
  });

  it('keeps excluded county geometry as context without offering it as a map link', () => {
    render(<CountiesPageClient />);
    const excluded = lamuPolygon();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'Mombasa' },
    });

    expect(excluded).toBeInTheDocument();
    expect(excluded).not.toHaveAttribute('role', 'link');
    expect(excluded).not.toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('link', { name: /^Mombasa, Grade:/ })).toHaveAttribute('tabindex', '0');
  });

  it.each(['click', 'Enter'] as const)(
    'does not navigate an excluded county through %s',
    (interaction) => {
      render(<CountiesPageClient />);
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
      render(<CountiesPageClient />);
      const excluded = lamuPolygon();
      fireEvent.focus(screen.getByRole('link', { name: /^Mombasa, Grade:/ }));
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
    render(<CountiesPageClient />);
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search County' }), {
      target: { value: 'No matching county' },
    });

    const map = screen.getByRole('region', { name: 'County Performance Map' });
    expect(within(map).queryAllByRole('link')).toHaveLength(0);
  });

  it('navigates a focused map polygon with Enter and retains the selected year', () => {
    render(<CountiesPageClient />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Year' }), {
      target: { value: 'FY2025/26 9M' },
    });
    fireEvent.keyDown(lamuPolygon(), { key: 'Enter' });
    expect(mockPush).toHaveBeenCalledWith('/counties/005?fy=FY2025%2F26%209M');
  });
});
