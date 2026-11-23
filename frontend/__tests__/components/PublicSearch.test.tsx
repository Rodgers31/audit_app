import PublicSearch from '@/components/search/PublicSearch';
import { findPublicArticles, type ArticleSearch } from '@/lib/search/publicSearch';
import { act, fireEvent, render, screen } from '@testing-library/react';

jest.mock('@/lib/i18n/LangProvider', () => ({ useLang: () => ({ lang: 'en' }) }));
jest.mock('@/lib/search/publicSearch', () => ({
  ...jest.requireActual('@/lib/search/publicSearch'),
  findPublicArticles: jest.fn(),
}));

beforeEach(() => {
  jest.useFakeTimers();
  jest.mocked(findPublicArticles).mockReset();
});
afterEach(() => jest.useRealTimers());

async function debounce() {
  await act(async () => { await jest.advanceTimersByTimeAsync(180); });
}

test('groups results by their public sources and keeps local results when the article index fails', async () => {
  jest.mocked(findPublicArticles).mockRejectedValueOnce(new Error('Unavailable'));
  render(<PublicSearch />);
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
  render(<PublicSearch autoFocus />);
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
