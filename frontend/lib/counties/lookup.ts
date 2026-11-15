import { REGION_COUNTIES, normalizeCountyName } from './regions';

export const COUNTY_LINKS = Object.values(REGION_COUNTIES).flat().map(name => ({
  name,
  slug: name.toLowerCase().replace(/'/g, '').replace(/\s+/g, '-'),
}));

export function findCounty(name: string) {
  const key = normalizeCountyName(name);
  return COUNTY_LINKS.find(county => normalizeCountyName(county.name) === key || (key === 'nairobicity' && county.slug === 'nairobi'));
}
