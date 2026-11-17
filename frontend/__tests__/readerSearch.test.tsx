import { type RunSearchResult, runSearch } from '@/data/constitution/search';
import ReaderSearch from '@/components/learn/constitution/ReaderSearch';
import { act, fireEvent, render, screen } from '@testing-library/react';

jest.mock('@/data/constitution/search', () => ({ runSearch: jest.fn() }));
jest.mock('@/lib/i18n/LangProvider', () => ({ useLang: () => ({ lang: 'en' }) }));

function pendingSearch() {
  let resolve!: (value: RunSearchResult) => void;
  const promise = new Promise<RunSearchResult>((done) => { resolve = done; });
  return { promise, resolve };
}

test('keeps the current reader query when an older search finishes last', async () => {
  jest.useFakeTimers();
  try {
    const older = pendingSearch();
    const current = pendingSearch();
    jest.mocked(runSearch).mockReturnValueOnce(older.promise).mockReturnValueOnce(current.promise);
    render(<ReaderSearch id='reader-search' open initialQuery='' onClose={jest.fn()} onSelect={jest.fn()} />);
    const input = screen.getByRole('searchbox', { name: 'Search Constitution articles' });

    fireEvent.change(input, { target: { value: 'devolution' } });
    await act(async () => { await jest.advanceTimersByTimeAsync(180); });
    expect(screen.getByRole('status')).toHaveTextContent('Searching articles');
    fireEvent.change(input, { target: { value: '214' } });
    await act(async () => { await jest.advanceTimersByTimeAsync(180); });
    expect(runSearch).toHaveBeenNthCalledWith(2, '214', 20, { includeSemantic: false });

    await act(async () => {
      current.resolve({
        mode: 'article',
        hits: [{
          article: { number: 214, title: 'Public debt' },
          chapter: { number: 12, title: 'Public Finance', summary: '', articleRange: [201, 231], articleTitles: [], dataPath: '' },
          isArticleLookup: true,
          score: 1,
        }],
      });
    });
    await act(async () => { older.resolve({ mode: 'keyword', hits: [] }); });

    expect(screen.getByRole('link', { name: /Art\. 214 Public debt/ })).toBeVisible();
    expect(screen.getByRole('status')).toHaveTextContent('1 matching article');
  } finally {
    jest.useRealTimers();
  }
});
