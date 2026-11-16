import { findChapterForArticle } from '@/data/constitution';

export const DEFAULT_READER_LOCATION = { chapter: 12, article: 229 };

export function readArticleLocation() {
  const article = new URLSearchParams(window.location.search).get('article');
  if (!article || !/^\d{1,3}$/.test(article)) return null;
  const number = Number(article);
  const chapter = findChapterForArticle(number);
  return chapter ? { chapter: chapter.number, article: number } : null;
}

export function pushArticleLocation(article: number) {
  const url = new URL(window.location.href);
  if (url.searchParams.get('article') === String(article)) return;
  url.searchParams.set('article', String(article));
  // Next's App Router handles the native history entry without a full navigation.
  window.history.pushState(null, '', url);
}
