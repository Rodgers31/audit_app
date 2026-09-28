import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import AuditListWithSources from '@/components/AuditListWithSources';

const mockUseCountyAuditList = jest.fn();
jest.mock('@/lib/react-query/useAudits', () => ({
  useCountyAuditList: (...args: unknown[]) => mockUseCountyAuditList(...args),
}));

const documentUrl = 'https://example.invalid/synthetic-county-audit.pdf?download=1#page=9&zoom=100';

function showSource(page: number | string | null, pageUrl: string) {
  mockUseCountyAuditList.mockReturnValue({
    data: {
      total: 1,
      page: 1,
      limit: 10,
      items: [{
        id: 1,
        description: 'Synthetic finding',
        source: { title: 'Synthetic audit', url: documentUrl, page, page_url: pageUrl },
      }],
    },
    isLoading: false,
    error: null,
  });
  render(<AuditListWithSources countyId='001' />);
  return screen.getByRole('link', { name: /open source/i });
}

describe('county audit source links', () => {
  it('opens the parsed PDF page and retains the existing zoom fragment', () => {
    const link = showSource(2, 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100&page=2');
    expect(link).toHaveAttribute('href', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100&page=2');
    expect(link).toHaveTextContent('page 2');
  });

  it('does not append a malformed reference or invent a page', () => {
    const link = showSource(null, 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100');
    expect(link).toHaveAttribute('href', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100');
    expect(link).not.toHaveTextContent(/page/i);
  });

  it('shows a textual annex locator without claiming a numeric PDF page', () => {
    const link = showSource('Annex VII', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100');
    expect(link).toHaveAttribute('href', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100');
    expect(link).toHaveTextContent('Annex VII');
    expect(link).not.toHaveTextContent('page Annex VII');
  });

  it('uses the resolved link even if an older response carries a textual page', () => {
    const link = showSource('pp. 38-39', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100&page=38');
    expect(link).toHaveAttribute('href', 'https://example.invalid/synthetic-county-audit.pdf?download=1#zoom=100&page=38');
  });

  it('opens the document without constructing a page when an older API omits page_url', () => {
    mockUseCountyAuditList.mockReturnValue({
      data: { total: 1, page: 1, limit: 10, items: [{
        id: 3,
        description: 'Synthetic legacy response',
        source: { url: documentUrl, page: 'p. 2' },
      }] },
      isLoading: false,
      error: null,
    });
    render(<AuditListWithSources countyId='001' />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', documentUrl);
    expect(link).not.toHaveTextContent(/page/i);
  });

  it('withholds a link when the source URL cannot be opened safely', () => {
    mockUseCountyAuditList.mockReturnValue({
      data: { total: 1, page: 1, limit: 10, items: [{
        id: 2,
        description: 'Synthetic finding with invalid URL',
        source: { url: 'javascript:alert(1)', page: 2, page_url: null },
      }] },
      isLoading: false,
      error: null,
    });
    render(<AuditListWithSources countyId='001' />);
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
