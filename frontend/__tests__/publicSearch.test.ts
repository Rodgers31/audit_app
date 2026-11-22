import { CONSTITUTION_META, loadAllChapters } from '@/data/constitution';
import { parseArticleNumber, runSearch } from '@/data/constitution/search';
import { findLocalPublicResults, findPublicArticles, hasPublicSearchQuery } from '@/lib/search/publicSearch';

jest.mock('@/data/constitution', () => ({
  ...jest.requireActual('@/data/constitution'),
  loadAllChapters: jest.fn(),
}));
jest.mock('@/data/constitution/search', () => ({
  parseArticleNumber: jest.fn(),
  runSearch: jest.fn(),
}));

test('uses canonical public county and glossary destinations from published indexes', () => {
  expect(findLocalPublicResults('Murang’a County').counties[0]).toEqual({
    title: "Murang'a",
    href: '/counties/Murang%27a',
  });
  expect(findLocalPublicResults('CoB').glossary[0]).toMatchObject({
    title: 'Controller of Budget',
    href: '/learn/glossary#term-controller-of-budget',
  });
  expect(findLocalPublicResults('supplier arrears').glossary[0]).toMatchObject({
    title: 'Pending bills',
    href: '/learn/glossary#term-pending-bills',
  });
  expect(hasPublicSearchQuery('ac')).toBe(false);
  expect(hasPublicSearchQuery('5')).toBe(true);
});

test('direct article lookup works without a full-text index', async () => {
  jest.mocked(parseArticleNumber).mockReturnValueOnce(214);
  jest.mocked(runSearch).mockResolvedValueOnce({
    mode: 'article',
    hits: [{ article: { title: 'Public debt', number: 214 }, chapter: CONSTITUTION_META[11], score: 100 }],
  });

  expect(await findPublicArticles('214')).toEqual({
    coverage: 'complete',
    articles: [{ title: 'Public debt', number: 214, href: '/learn?article=214' }],
  });
  expect(loadAllChapters).not.toHaveBeenCalled();
});

test('distinguishes an unavailable or partially loaded Constitution index from a complete empty search', async () => {
  jest.mocked(parseArticleNumber).mockReturnValue(null);
  const chapters = CONSTITUTION_META.map(({ number, title, summary }) => ({ number, title, summary, articles: [] }));
  jest.mocked(loadAllChapters)
    .mockResolvedValueOnce([])
    .mockResolvedValueOnce(chapters.slice(0, -1))
    .mockResolvedValueOnce(chapters);
  jest.mocked(runSearch).mockResolvedValue({ mode: 'keyword', hits: [] });

  expect(await findPublicArticles('appropriation')).toEqual({ coverage: 'unavailable', articles: [] });
  expect(await findPublicArticles('appropriation')).toEqual({ coverage: 'partial', articles: [] });
  expect(await findPublicArticles('appropriation')).toEqual({ coverage: 'complete', articles: [] });
  expect(runSearch).toHaveBeenLastCalledWith('appropriation', 5, { includeSemantic: false });
});
