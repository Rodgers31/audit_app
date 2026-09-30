import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';

let statistics: any;
jest.mock('@/lib/react-query/useAudits', () => ({
  useAuditStatistics: () => ({ data: statistics, isLoading: false, error: null }),
}));
jest.mock('framer-motion', () => ({
  motion: {
    div: ({ children, initial: _initial, whileInView: _whileInView,
            viewport: _viewport, transition: _transition, ...props }: any) => (
      <div {...props}>{children}</div>
    ),
  },
}));

import AccountabilityPulseCard from '@/components/dashboard/AccountabilityPulseCard';

const base = {
  total_findings: 3,
  counties_audited: 1,
  by_severity: { critical: 0, warning: 3, info: 0 },
  top_flagged_counties: [],
  recent_critical: [],
  total_amount_flagged: 5.25,
  total_amount_flagged_reason: null,
  findings_with_amount: 2,
  findings_with_invalid_amount: 1,
  findings_with_ambiguous_text_amount: 0,
  findings_without_amount: 0,
};

describe('audit statistics amount coverage', () => {
  it('labels a partial sum and names withheld invalid amounts', () => {
    statistics = base;
    render(<AccountabilityPulseCard />);
    expect(screen.getByText('KES 5.25')).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 findings have a usable amount/)).toBeInTheDocument();
    expect(screen.getByText(/1 invalid stored amount withheld/)).toBeInTheDocument();
  });

  it('does not turn all-invalid coverage into a zero figure', () => {
    statistics = { ...base, total_findings: 1, by_severity: { warning: 1 },
      total_amount_flagged: null, total_amount_flagged_reason: 'invalid_stored_amount',
      findings_with_amount: 0 };
    render(<AccountabilityPulseCard />);
    expect(screen.getByText('Amount total unavailable')).toBeInTheDocument();
    expect(screen.queryByText('KES 0')).not.toBeInTheDocument();
  });

  it('shows sourced zero and absent coverage distinctly', () => {
    statistics = { ...base, total_findings: 2, by_severity: { warning: 2 },
      total_amount_flagged: 0, findings_with_amount: 1,
      findings_with_invalid_amount: 0, findings_without_amount: 1 };
    render(<AccountabilityPulseCard />);
    expect(screen.getByText('KES 0')).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 findings have a usable amount/)).toBeInTheDocument();
    expect(screen.getByText(/1 finding lacks a usable numeric amount/)).toBeInTheDocument();
  });

  it('distinguishes ambiguous amount text from a finding with no figure', () => {
    statistics = { ...base, total_findings: 1, by_severity: { warning: 1 },
      total_amount_flagged: null, total_amount_flagged_reason: 'ambiguous_text_amount',
      findings_with_amount: 0, findings_with_invalid_amount: 0,
      findings_with_ambiguous_text_amount: 1, findings_without_amount: 1 };
    render(<AccountabilityPulseCard />);
    expect(screen.getByText('Amount total unavailable')).toBeInTheDocument();
    expect(screen.getByText(/1 finding lacks a usable numeric amount/)).toBeInTheDocument();
    expect(screen.getByText(/1 finding has amount text that needs source review/)).toBeInTheDocument();
    expect(screen.queryByText(/no recorded amount/)).not.toBeInTheDocument();
  });

  it('withholds the figure when an older payload lacks coverage fields', () => {
    statistics = { total_findings: 1, counties_audited: 1,
      total_amount_flagged: 50, by_severity: { warning: 1 },
      top_flagged_counties: [], recent_critical: [] };
    render(<AccountabilityPulseCard />);
    expect(screen.getByText('Amount total unavailable')).toBeInTheDocument();
    expect(screen.getByText('Audit amount coverage unavailable')).toBeInTheDocument();
    expect(screen.queryByText('KES 50')).not.toBeInTheDocument();
  });
});
