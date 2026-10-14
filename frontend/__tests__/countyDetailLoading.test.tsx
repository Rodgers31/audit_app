import { render, screen } from '@testing-library/react';
import CountyDetailLoading from '@/app/counties/[id]/loading';

jest.mock('@/lib/i18n/LangProvider', () => ({
  useLang: () => ({
    t: (key: string) => ({
      'county.page.title_fallback': 'County Detail',
      'county.loading': 'Loading county details…',
    }[key] ?? key),
  }),
}));

it('shows a busy county shell without inventing financial data or a fiscal year', () => {
  render(<CountyDetailLoading />);
  expect(screen.getByRole('heading', { level: 1, name: 'County Detail' })).toBeInTheDocument();
  expect(screen.getByText('Loading county details…')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
  expect(screen.queryByText(/KES|2024\/25|available|unavailable/i)).not.toBeInTheDocument();
});
