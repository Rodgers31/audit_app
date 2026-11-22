import { glossaryTerms } from '@/data/glossaryTerms';
import { COUNTY_LINKS } from '@/lib/counties/lookup';
import { normalizeCountyName } from '@/lib/counties/regions';

const RESULTS_PER_GROUP = 5;

interface PublicSearchResult {
  href: string;
  title: string;
}

interface SearchEntry extends PublicSearchResult {
  keys: string[];
}

const counties: SearchEntry[] = COUNTY_LINKS.map(({ name, slug }) => ({
  href: `/counties/${slug}`,
  title: name,
  keys: [normalizeCountyName(name)],
}));

const glossary: SearchEntry[] = glossaryTerms.map(({ id, term, abbreviation, aliases }) => ({
  href: `/learn/glossary#term-${id}`,
  title: term,
  keys: [term, ...(abbreviation ? [abbreviation] : []), ...(aliases ?? [])].map(normalizeTerm),
}));

function normalizeTerm(text: string) {
  return text
    .trim()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

function findMatches(entries: SearchEntry[], query: string): PublicSearchResult[] {
  if (!query) return [];

  return entries
    .map(({ keys, title, href }) => {
      const rank = keys.includes(query) ? 0
        : keys.some(key => key.startsWith(query)) ? 1
        : keys.some(key => key.includes(query)) ? 2
        : 3;
      return { title, href, rank };
    })
    .filter(({ rank }) => rank < 3)
    .sort((a, b) => a.rank - b.rank || a.title.localeCompare(b.title, 'en-KE'))
    .slice(0, RESULTS_PER_GROUP)
    .map(({ title, href }) => ({ title, href }));
}

export function hasPublicSearchQuery(query: string) {
  return query.length >= 3 || /^\d{1,2}$/.test(query);
}

export function findLocalPublicResults(query: string) {
  return {
    counties: findMatches(counties, normalizeCountyName(query)),
    glossary: findMatches(glossary, normalizeTerm(query)),
  };
}

export interface ArticleSearchResult extends PublicSearchResult {
  number: number;
}

export interface ArticleSearch {
  coverage: 'complete' | 'partial' | 'unavailable';
  articles: ArticleSearchResult[];
}

export async function findPublicArticles(query: string): Promise<ArticleSearch> {
  const { runSearch, parseArticleNumber } = await import('@/data/constitution/search');
  let coverage: ArticleSearch['coverage'] = 'complete';

  // Direct lookups use the published metadata. Keyword search can return an
  // incomplete index when a chapter request fails, even if the search succeeds.
  if (parseArticleNumber(query) === null) {
    const { CONSTITUTION_META, loadAllChapters } = await import('@/data/constitution');
    const chapters = await loadAllChapters();
    if (chapters.length === 0) return { coverage: 'unavailable', articles: [] };
    const loaded = new Set(chapters.map(chapter => chapter.number));
    if (CONSTITUTION_META.some(chapter => !loaded.has(chapter.number))) coverage = 'partial';
  }

  const { hits } = await runSearch(query, RESULTS_PER_GROUP, { includeSemantic: false });
  return {
    coverage,
    articles: hits.slice(0, RESULTS_PER_GROUP).map(({ article }) => ({
      href: `/learn?article=${article.number}`,
      number: article.number,
      title: article.title,
    })),
  };
}
