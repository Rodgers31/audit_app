import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import mixed from '../fixtures/auditStatistics.mixed.json';
import { getAuditStatistics } from '@/lib/api/audits';

let payload: any = mixed;
let statistics: any;
jest.mock('@/lib/api/axios', () => ({
  apiClient: { get: jest.fn(async () => ({ data: payload })) },
}));
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

beforeEach(() => { payload = mixed; });

it('carries the real flat statistics response through the service to the card', async () => {
  statistics = await getAuditStatistics();
  expect(statistics).toEqual(mixed);
  render(<AccountabilityPulseCard />);
  expect(screen.getByText(/4 total/)).toBeInTheDocument();
  expect(screen.getByText('KES 600')).toBeInTheDocument();
  expect(screen.getByText(/1 Kenyan counties covered/)).toBeInTheDocument();
  expect(screen.getByText('Most Flagged Kenyan Counties')).toBeInTheDocument();
  expect(screen.getByText('Test')).toBeInTheDocument();
  expect(screen.getByText('2 critical')).toBeInTheDocument();
  expect(screen.getByText('Foreign County · FY2024/25')).toBeInTheDocument();
});

it('displays an empty database as zero findings', async () => {
  payload = { ...mixed, total_findings: 0, counties_audited: 0,
    by_severity: {}, top_flagged_counties: [], recent_critical: [],
    total_amount_flagged: null, findings_with_amount: 0 };
  // Isolate empty rendering from the service boundary tested above.
  statistics = payload;
  render(<AccountabilityPulseCard />);
  expect(screen.getByText('0 total')).toBeInTheDocument();
  expect(screen.queryByText('KES 600')).not.toBeInTheDocument();
});


it.each(['Synthetic Ministry', 'Foreign County', 'Test County'])(
  'uses the institution identity for recent findings from %s', (entityName) => {
    statistics = { ...mixed, recent_critical: mixed.recent_critical.filter(
      (row) => row.entity_name === entityName) };
    render(<AccountabilityPulseCard />);
    expect(screen.getByText(`${entityName} · FY2024/25`)).toBeInTheDocument();
    expect(screen.getByText('KES 600')).toBeInTheDocument();
  }
);

it('retains compatibility with recent items from an older backend', () => {
  statistics = { ...mixed, recent_critical: [{ ...mixed.recent_critical[0],
    entity_name: undefined, county: 'Legacy institution' }] };
  render(<AccountabilityPulseCard />);
  expect(screen.getByText('Legacy institution · FY2024/25')).toBeInTheDocument();
});
