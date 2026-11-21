import sitemap from '@/app/sitemap';
import { COUNTY_LINKS } from '@/lib/counties/lookup';

const publicPaths = [
  '/', '/debt', '/budget', '/counties', '/transparency', '/learn', '/learn/glossary',
  '/learn/government', '/learn/quiz', '/about', '/privacy', '/terms', '/audits', '/sources',
  '/counties/compare', '/accountability/unaccounted-funds', '/learn/why-it-matters',
];

it('lists the existing pages and the newly indexed public routes once', () => {
  const urls = sitemap().map(entry => new URL(entry.url));
  const paths = urls.map(url => url.pathname);
  const countyPaths = COUNTY_LINKS.map(({ slug }) => `/counties/${slug}`);

  expect(paths).toHaveLength(64);
  expect(new Set(paths).size).toBe(paths.length);
  expect(paths.sort()).toEqual([...publicPaths, ...countyPaths].sort());
  expect(urls.every(url => url.origin === urls[0].origin && !url.search && !url.hash)).toBe(true);
});

it('uses all 47 county links, keeping the encoded apostrophe and hyphenated names', () => {
  const countyUrls = sitemap().filter(({ url }) =>
    new URL(url).pathname.startsWith('/counties/') && !url.endsWith('/counties/compare'));
  const paths = countyUrls.map(({ url }) => new URL(url).pathname);

  expect(paths).toHaveLength(47);
  expect(paths).toEqual(expect.arrayContaining([
    '/counties/Murang%27a', '/counties/elgeyo-marakwet', '/counties/tharaka-nithi', '/counties/nairobi',
  ]));
  expect(paths).not.toContain('/counties/muranga');
  expect(paths).not.toContain('/counties/001');
});

it('does not report a modification date without a published freshness source', () => {
  expect(sitemap().every(entry => entry.lastModified === undefined)).toBe(true);
});
