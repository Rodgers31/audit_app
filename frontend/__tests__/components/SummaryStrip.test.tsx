import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

jest.mock('@/lib/react-query/useDebt', () => ({
  useDebtTimeline: () => ({ data: undefined }),
  useNationalDebtOverview: () => ({ data: undefined }),
}));

// The strip reads the statutory debt anchor from the fiscal summary. Mocked
// as unavailable here: this file's subject is what the strip says when it has
// no data at all.
jest.mock('@/lib/react-query/useFiscal', () => ({
  useFiscalSummary: () => ({ data: undefined }),
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
    // An unassessable ratio is not a breach of the anchor, and must not be
    // dressed as one — nor as quiet compliance.
    expect(screen.queryByText(/above the .* anchor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/debt distress/i)).not.toBeInTheDocument();
  });
});
