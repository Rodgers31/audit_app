import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => ({ data: undefined }),
  useNationalDebtOverview: () => ({ data: undefined }),
}));

jest.mock('@/components/ui/KenyaFlag', () => ({
  KenyaFlag: () => <span aria-label='Kenya' />,
}));

jest.mock('@/components/dashboard/DebtExplainerModal', () => ({
  __esModule: true,
  default: () => null,
}));

import { SummaryStrip } from '@/components/dashboard/HeroSection';

describe('SummaryStrip missing-data state', () => {
  it('does not fabricate units or a risk rating when the API is unavailable', () => {
    render(<SummaryStrip />);

    expect(screen.getByText('Not assessed')).toBeInTheDocument();
    expect(screen.queryByText(/moderate risk/i)).not.toBeInTheDocument();
    expect(screen.queryByText('—T')).not.toBeInTheDocument();
    expect(screen.queryByText('—%')).not.toBeInTheDocument();
  });
});
