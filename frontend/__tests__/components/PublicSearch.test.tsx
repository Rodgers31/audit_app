import PublicSearch from '@/components/search/PublicSearch';
import { getAuditFindings, type FindingDetailItem, type FindingsListData } from '@/lib/api/audits';
import { getNationalLoans, type NationalLoan, type NationalLoansResponse } from '@/lib/api/debt';
import { findPublicArticles, type ArticleSearch } from '@/lib/search/publicSearch';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import type { ComponentProps } from 'react';

let mockLang = 'en';
jest.mock('@/lib/i18n/LangProvider', () => ({ useLang: () => ({ lang: mockLang }) }));
jest.mock('@/lib/api/audits', () => ({ getAuditFindings: jest.fn() }));
jest.mock('@/lib/api/debt', () => ({ getNationalLoans: jest.fn() }));
jest.mock('@/lib/search/publicSearch', () => ({
  ...jest.requireActual('@/lib/search/publicSearch'),
  findPublicArticles: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
  mockLang = 'en';
  jest.mocked(findPublicArticles).mockReset().mockResolvedValue({ coverage: 'complete', articles: [] });
  jest.mocked(getAuditFindings).mockReset().mockResolvedValue(listFindings());
  jest.mocked(getNationalLoans).mockReset().mockResolvedValue(listLoans());
});
afterEach(() => jest.useRealTimers());

function renderSearch(props: ComponentProps<typeof PublicSearch> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
  return render(<QueryClientProvider client={client}><PublicSearch {...props} /></QueryClientProvider>);
}

function listFindings(items: FindingDetailItem[] = []): FindingsListData {
  return { items, total: items.length, page: 1, limit: 100 };
}

function finding(id: number, overrides: Partial<FindingDetailItem> = {}): FindingDetailItem {
  return {
    id, entity_id: 12, period_id: 1, county_name: null, audit_year: 2025,
    audited_entity_name: 'Synthetic public works office', finding_text: 'The procurement records were missing.',
    finding_title: 'Road procurement', page_ref: 'pp. 17–18',
    source_document_url: 'https://example.org/audit.pdf#page=17', severity: 'warning',
    recommended_action: null, query_type: null, amount: null, status: null, audit_opinion: null,
    follow_up_status: null, external_reference: null, management_response: null, confidence_score: null,
    ...overrides,
  };
}

function listLoans(...lenderNames: string[]): NationalLoansResponse {
  return {
    loans: lenderNames.map(lender => ({ lender }) as NationalLoan), total_loans: lenderNames.length,
    total_outstanding: null, total_annual_service_cost: null,
    annual_debt_service: { value_kes: null, absent_reason: null }, source: '', source_url: '',
  };
}

async function debounce() {
  await act(async () => { await jest.advanceTimersByTimeAsync(180); });
}

test('groups results by their public sources and keeps local results when the article index fails', async () => {
  jest.mocked(findPublicArticles).mockRejectedValueOnce(new Error('Unavailable'));
  renderSearch();
  const field = screen.getByRole('searchbox', { name: 'Search AuditGava' });

  fireEvent.change(field, { target: { value: 'Nairobi' } });
  expect(screen.getByRole('region', { name: 'Counties' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Nairobi' })).toHaveAttribute('href', '/counties/nairobi');
  await debounce();
  expect(screen.getByRole('status')).toHaveTextContent('One result shown. Constitution article search is unavailable.');
  expect(screen.getByRole('status')).not.toHaveTextContent('No matching');

  fireEvent.click(screen.getByRole('button', { name: 'Clear search' }));
  expect(field).toHaveFocus();
  expect(field).toHaveValue('');
  expect(screen.queryByRole('link', { name: 'Nairobi' })).not.toBeInTheDocument();
});

test('ignores an earlier result that resolves after a newer query', async () => {
  let finishOld!: (value: ArticleSearch) => void;
  jest.mocked(findPublicArticles)
    .mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }))
    .mockResolvedValueOnce({
      coverage: 'partial',
      articles: [{ number: 214, title: 'Public debt', href: '/learn?article=214' }],
    });
  renderSearch({ autoFocus: true });
  const field = screen.getByRole('searchbox');
  expect(field).toHaveFocus();

  fireEvent.change(field, { target: { value: 'borrow' } });
  await debounce();
  fireEvent.change(field, { target: { value: '214' } });
  await debounce();
  await act(async () => finishOld({ coverage: 'complete', articles: [] }));

  expect(screen.getByRole('region', { name: 'Constitution articles' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Article 214 Public debt' })).toHaveAttribute('href', '/learn?article=214');
  expect(screen.getByRole('status')).toHaveTextContent('One result shown. Some Constitution article text is unavailable.');
});

test('links only audit matches with an exact cited PDF page, even when multiple findings share that page', async () => {
  jest.mocked(getAuditFindings).mockResolvedValue(listFindings([
    finding(1),
    finding(2, { finding_title: null, finding_text: 'Road procurement costs were unsupported.' }),
    finding(3, { finding_title: 'Road missing page', page_ref: 'Annex A' }),
    finding(4, { finding_title: 'Road mismatched page', source_document_url: 'https://example.org/audit.pdf#page=12' }),
    finding(5, { finding_title: 'Road missing URL', source_document_url: null }),
    finding(6, { finding_title: 'Road document only', source_document_url: 'https://example.org/audit.pdf' }),
    finding(7, { finding_title: 'Road unsafe URL', source_document_url: 'javascript:void(0)' }),
    finding(8, { finding_title: 'Road reversed range', page_ref: 'pp. 17–16' }),
  ]));
  const onNavigate = jest.fn();
  renderSearch({ onNavigate });
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'road' } });
  await debounce();

  expect(getAuditFindings).toHaveBeenCalledWith({ page: 1, limit: 100 }, expect.any(AbortSignal));
  const links = within(screen.getByRole('region', { name: 'Audit findings' })).getAllByRole('link');
  expect(links).toHaveLength(2);
  expect(links[0]).toHaveAccessibleName('Road procurement Synthetic public works office Open cited report page');
  expect(links[1]).toHaveTextContent('Road procurement costs were unsupported.');
  for (const link of links) expect(link).toHaveAttribute('href', 'https://example.org/audit.pdf#page=17');
  expect(screen.getByText('Audit search checks up to 100 of the newest published findings and shows matches with cited report pages.')).toBeVisible();
  links[0].addEventListener('click', event => event.preventDefault());
  fireEvent.click(links[0], { ctrlKey: true });
  expect(onNavigate).not.toHaveBeenCalled();
  fireEvent.click(links[0]);
  expect(onNavigate).toHaveBeenCalledTimes(1);
});

test('updates matching over a delayed snapshot, keeping valid lender results when audits fail', async () => {
  let resolveLoans!: (value: NationalLoansResponse) => void;
  jest.mocked(getNationalLoans).mockImplementation(() => new Promise(resolve => { resolveLoans = resolve; }));
  jest.mocked(getAuditFindings).mockRejectedValue(new Error('Unavailable'));
  renderSearch();
  const input = screen.getByRole('searchbox');
  fireEvent.change(input, { target: { value: 'Old bank' } });
  await debounce();
  expect(screen.getByRole('status')).toHaveTextContent('Searching… Audit findings search is unavailable.');

  fireEvent.change(input, { target: { value: 'new bank water' } });
  await act(async () => resolveLoans(listLoans('Old Bank', 'New Bank (Water & Energy  )', 'New Bank (Water & Energy)')));
  await debounce();
  const links = within(screen.getByRole('region', { name: 'Lenders' })).getAllByRole('link');
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAccessibleName('New Bank (Water & Energy) Open loan register');
  expect(links[0]).toHaveAttribute('href', '/debt?lender=New+Bank+%28Water+%26+Energy%29#loan-register');
  expect(screen.queryByText('Old Bank')).not.toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('One result shown. Audit findings search is unavailable.');
  expect(getNationalLoans).toHaveBeenCalledTimes(1);
});

test('a ministry label with no public destination does not create a group or result', async () => {
  jest.mocked(getAuditFindings).mockResolvedValue(listFindings([finding(1, {
    audited_entity_name: 'Ministry of Synthetic Testing',
  })]));
  renderSearch();
  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Ministry of Synthetic Testing' } });
  await debounce();
  const links = screen.getAllByRole('link');
  expect(links).toHaveLength(1);
  expect(links[0]).toHaveAttribute('href', 'https://example.org/audit.pdf#page=17');
  expect(screen.queryByRole('region', { name: 'Ministries' })).not.toBeInTheDocument();

  fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Ministry of Another Fixture' } });
  await debounce();
  expect(screen.getByRole('status')).toHaveTextContent('No matches in the sources searched.');
  expect(screen.queryByRole('link')).not.toBeInTheDocument();
});

test.each([
  ['sw', 'Tafuta kaunti, matokeo ya ukaguzi au istilahi', 'Matokeo ya ukaguzi', 'Wakopeshaji', 'Fungua ukurasa uliotajwa katika ripoti', 'Fungua rejesta ya mikopo'],
  ['plain', 'Search counties, audit findings, terms', 'Audit findings', 'Lenders', 'Read the finding on the cited report page', 'View this lender in the loan register'],
])('localizes the compact field and new group actions in %s', async (lang, placeholder, audits, lenders, report, register) => {
  mockLang = lang;
  jest.mocked(getAuditFindings).mockResolvedValue(listFindings([finding(1)]));
  jest.mocked(getNationalLoans).mockResolvedValue(listLoans('Synthetic Road Credit Union'));
  renderSearch({ compact: true });
  fireEvent.change(screen.getByPlaceholderText(placeholder), { target: { value: 'road' } });
  await debounce();
  expect(within(screen.getByRole('region', { name: audits })).getByRole('link')).toHaveAccessibleName(expect.stringContaining(report));
  expect(within(screen.getByRole('region', { name: lenders })).getByRole('link')).toHaveAccessibleName(expect.stringContaining(register));
});
