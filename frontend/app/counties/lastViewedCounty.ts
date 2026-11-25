import { COUNTY_LINKS } from '@/lib/counties/lookup';
import { normalizeCountyName } from '@/lib/counties/regions';

const storageKey = 'auditgava:last-viewed-county';
const countyBySlug = new Map(COUNTY_LINKS.map(county => [county.slug, county]));
const countyByName = new Map(COUNTY_LINKS.map(county => [normalizeCountyName(county.name), county]));

export function canonicalCounty(name: string) {
  const key = normalizeCountyName(name);
  return countyByName.get(key === 'nairobicity' ? 'nairobi' : key);
}

export function readLastViewedCounty() {
  try {
    const slug = window.localStorage.getItem(storageKey);
    return slug ? countyBySlug.get(slug) ?? null : null;
  } catch {
    return null;
  }
}

export const readServerCounty = () => null;

const listeners = new Set<() => void>();

export function subscribeLastViewedCounty(listener: () => void) {
  function syncStorage(event: StorageEvent) {
    if (event.key === storageKey || event.key === null) listener();
  }

  listeners.add(listener);
  window.addEventListener('storage', syncStorage);
  window.addEventListener('pageshow', listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', syncStorage);
    window.removeEventListener('pageshow', listener);
  };
}

export function rememberCounty(name: string) {
  const county = canonicalCounty(name);
  if (!county) return;
  try {
    if (window.localStorage.getItem(storageKey) === county.slug) return;
    window.localStorage.setItem(storageKey, county.slug);
  } catch {
    return;
  }
  listeners.forEach(listener => listener());
}
