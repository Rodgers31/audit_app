import { render, screen } from '@testing-library/react';
import AuditSeverity from '@/app/audits/AuditSeverity';
import { useAuditStatistics } from '@/lib/react-query/useAudits';

jest.mock('@/lib/react-query/useAudits', () => ({ useAuditStatistics: jest.fn() }));

const stats = jest.mocked(useAuditStatistics);
const response = (data: unknown, state = {}) => {
  stats.mockReturnValue({ data, isPending: false, isError: false, ...state } as ReturnType<typeof useAuditStatistics>);
};

describe('audit severity scopes', () => {
  it.each([
    [undefined, 10, 'Severity counts are unavailable.'],
    [{ total_findings: 10 }, 10, 'Severity counts are unavailable.'],
    [{ total_findings: 0, by_severity: {} }, 0, 'The collection contains no published findings to group by severity.'],
    [{ total_findings: 10, by_severity: { unknown: 10 } }, 10, 'Published findings are available, but no severity counts were recorded for them.'],
    [{ total_findings: 10, by_severity: {} }, 10, 'Published findings are available, but no severity counts were recorded for them.'],
    [{ total_findings: 10, by_severity: { critical: 11 } }, 10, 'The reported severity counts could not be reconciled.'],
    [{ total_findings: 10, by_severity: { critical: -1 } }, 10, 'The reported severity counts could not be reconciled.'],
    [{ total_findings: 10, by_severity: { critical: 1.5 } }, 10, 'The reported severity counts could not be reconciled.'],
    [{ total_findings: 10, by_severity: { critical: '10' } }, 10, 'The reported severity counts could not be reconciled.'],
    [{ total_findings: 10, by_severity: { critical: 10 }, _meta: { entity_scope: 'county' } }, 10, 'The reported severity counts could not be reconciled.'],
    [{ total_findings: 10, by_severity: { critical: 10 } }, 9, 'The severity counts could not be matched to the published findings total above.'],
    [{ total_findings: 10, by_severity: { critical: 10 } }, undefined, 'The severity counts could not be matched to the published findings total above.'],
  ])('describes insufficient evidence for a whole (%#)', (data, total, note) => {
    response(data);
    const { container } = render(<AuditSeverity collectionTotal={total} retryCollection={jest.fn()} />);
    expect(screen.getByText(note)).toBeVisible();
    expect(container.querySelector('[data-severity-plot]')).toBeNull();
    expect(screen.queryByRole('list')).toBeNull();
  });

  it('withholds a complete bar for a subset and keeps an explicit true zero', () => {
    response({ total_findings: 10, by_severity: { critical: 0, warning: 7 } });
    const { container } = render(<AuditSeverity collectionTotal={10} retryCollection={jest.fn()} />);
    expect(screen.getByText('Severity counts are available for 7 of 10 published findings in this collection.')).toBeVisible();
    expect(screen.getAllByRole('listitem').map(item => item.textContent)).toEqual(['Serious 0', 'Warning 7']);
    expect(container.querySelector('[data-severity-plot]')).toBeNull();
  });

  it('makes an inferred zero visible only after counts reconcile', () => {
    response({ total_findings: 10, by_severity: { warning: 10 } });
    const { container } = render(<AuditSeverity collectionTotal={10} retryCollection={jest.fn()} />);
    expect(screen.getByRole('button', { name: 'Serious 0' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Note 0' })).toBeVisible();
    expect(container.querySelectorAll('[data-severity]')).toHaveLength(1);
  });

  it('keeps loading distinct from a request failure', () => {
    response(undefined, { isPending: true });
    const { rerender } = render(<AuditSeverity collectionTotal={10} retryCollection={jest.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading severity counts');
    expect(screen.queryByRole('alert')).toBeNull();
    response(undefined, { isError: true });
    rerender(<AuditSeverity collectionTotal={10} retryCollection={jest.fn()} />);
    expect(screen.getByRole('alert')).toHaveTextContent('Severity counts could not be loaded.');
  });
});
