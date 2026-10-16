import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import CountiesPageClient from '@/app/counties/CountiesPageClient';
import type { CountyFiscalYears } from '@/lib/utils';

let mockYears: CountyFiscalYears | undefined;
const mockUseCounties = jest.fn((..._args: unknown[]) => ({ data: [], isLoading: false, error: null }));
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
jest.mock('@/lib/react-query', () => ({
  useCounties: (...args: unknown[]) => mockUseCounties(...args),
  useCountyFiscalYears: () => ({ data: mockYears }),
}));
jest.mock('@/components/DataFreshnessBadge', () => ({ __esModule: true, default: () => null }));

const years: CountyFiscalYears = {
  years: ['FY2025/26 9M', 'FY2024/25'].map(label => ({ label, source: 'cob_cbirr', counties: 47 })),
  default: 'FY2024/25',
};
beforeEach(() => { mockYears = undefined; mockUseCounties.mockClear(); });

it('reserves the same year field before metadata arrives without exposing an empty picker', () => {
  const view = render(<CountiesPageClient />);
  expect(screen.queryByRole('combobox', { name: 'Year' })).not.toBeInTheDocument();
  const reservedSelect = view.container.querySelector('header select');
  expect(reservedSelect).toBeInTheDocument();
  expect(reservedSelect).toBeDisabled();
  expect(reservedSelect?.closest('label')).toHaveAttribute('aria-hidden', 'true');
  expect(reservedSelect?.closest('label')).toHaveClass('yearField');
  expect(mockUseCounties).toHaveBeenLastCalledWith({ fiscalYear: undefined });

  mockYears = years;
  view.rerender(<CountiesPageClient />);
  const picker = screen.getByRole('combobox', { name: 'Year' });
  expect(picker).toBe(reservedSelect);
  expect(picker).toBeEnabled();
  expect(picker.closest('label')).toHaveClass('yearField');
  expect(picker).toHaveValue('FY2024/25');
  fireEvent.change(picker, { target: { value: 'FY2025/26 9M' } });
  expect(mockUseCounties).toHaveBeenLastCalledWith({ fiscalYear: 'FY2025/26 9M' });
});

it('keeps absent and empty metadata inert without inventing a year', () => {
  mockYears = { years: [], default: null };
  const view = render(<CountiesPageClient />);
  expect(screen.queryByRole('combobox', { name: 'Year' })).not.toBeInTheDocument();
  expect(view.container.querySelector('header select')).toBeDisabled();
  expect(view.container.querySelector('header select')).toHaveTextContent('');
  expect(mockUseCounties).toHaveBeenLastCalledWith({ fiscalYear: undefined });
});
