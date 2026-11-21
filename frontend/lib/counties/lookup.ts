import { normalizeCountyName, REGION_COUNTIES } from './regions';

export const COUNTY_LINKS = Object.values(REGION_COUNTIES).flat().map(name => ({
  name,
  // The county API accepts the official name with its apostrophe preserved.
  slug: name === "Murang'a" ? 'Murang%27a' : name.toLowerCase().replace(/'/g, '').replace(/\s+/g, '-'),
}));

const searchableCounties = COUNTY_LINKS.map(({ name, slug }) => ({
  name,
  href: `/counties/${slug}`,
  key: normalizeCountyName(name),
})).sort((a, b) => a.name.localeCompare(b.name, 'en-KE'));

export function findCountyLinks(query: string) {
  const term = normalizeCountyName(query);
  if (!term) return [];
  return searchableCounties.filter(({ key }) => key.includes(term)).sort(
    (a, b) => Number(b.key === term) - Number(a.key === term) ||
      Number(b.key.startsWith(term)) - Number(a.key.startsWith(term))
  );
}
