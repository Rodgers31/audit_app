import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { resolveCountyMetadataRoute } from '@/app/counties/[id]/countyMetadata';
import { COUNTY_LINKS } from '@/lib/counties/lookup';

import { generateMetadata } from '@/app/counties/[id]/page';
import type { ResolvingMetadata } from 'next';

jest.mock('@/app/counties/[id]/CountyDetailClient', () => ({
  __esModule: true,
  default: () => null,
}));
jest.mock('@/lib/api/counties', () => ({ getCountyComprehensive: jest.fn() }));
jest.mock('@/lib/react-query/getQueryClient', () => ({ getQueryClient: jest.fn() }));

it('describes county accountability without fetching data or advertising withdrawn projects', async () => {
  const parent = Promise.resolve({}) as ResolvingMetadata;
  const metadata = await generateMetadata({ params: Promise.resolve({ id: '001' }) }, parent);
  expect(metadata.description).toMatch(/Nairobi County’s.*accountability/i);
  expect(metadata.description).not.toMatch(/stalled projects/i);
  const { getCountyComprehensive } = jest.requireMock('@/lib/api/counties');
  expect(getCountyComprehensive).not.toHaveBeenCalled();
});

function readCountyCodes(path: string, variable: string): [string, string][] {
  const source = readFileSync(resolve(__dirname, '../../backend', path), 'utf8');
  const block = source.split(`${variable} = {\n`)[1]?.split('\n}')[0] ?? '';
  return Array.from(block.matchAll(/^\s*"(\d{3})": "([^"]+)",$/gm), ([, code, name]) => [code, name]);
}

describe('county metadata route identity', () => {
  it('resolves every canonical county link from its Next route segment', () => {
    expect(COUNTY_LINKS).toHaveLength(47);
    for (const county of COUNTY_LINKS) {
      expect(resolveCountyMetadataRoute(county.slug)).toEqual(county);
    }
  });

  it('agrees with both complete backend code namespaces', () => {
    const official = readCountyCodes('services/county_identity.py', 'OFFICIAL_COUNTY_CODES');
    const legacy = readCountyCodes('main.py', 'COUNTY_MAPPING');
    expect(official).toHaveLength(47);
    expect(legacy).toHaveLength(47);
    for (const [code, name] of official) {
      expect(resolveCountyMetadataRoute(`code:${code}`)?.name).toBe(name);
    }
    for (const [id, name] of legacy) {
      expect(resolveCountyMetadataRoute(id)?.name).toBe(name);
    }
  });

  it.each([
    ["Murang'a", "Murang'a", 'Murang%27a'],
    ['Murang%E2%80%99a', "Murang'a", 'Murang%27a'],
    ['Taita%20Taveta', 'Taita Taveta', 'taita-taveta'],
    ['code%3A001', 'Mombasa', 'mombasa'],
    ['Taita Taveta County', 'Taita Taveta', 'taita-taveta'],
    ['TAITA-TAVETA', 'Taita Taveta', 'taita-taveta'],
    ['Nairobi City', 'Nairobi', 'nairobi'],
    ['nairobi-city', 'Nairobi', 'nairobi'],
  ])('resolves supported alias %s to the canonical route', (id, name, slug) => {
    expect(resolveCountyMetadataRoute(id)).toEqual({ name, slug });
  });

  it.each(['4', '0047', '000', '048', 'code:048', 'muranga', 'murang-a', 'Murang%2527a', 'Taita%2520Taveta', 'taitataveta', 'taita%2Ftaveta', '%E2%80', 'unknown-county'])('cannot attribute %s to a county', id => {
    expect(resolveCountyMetadataRoute(id)).toBeUndefined();
  });
});
