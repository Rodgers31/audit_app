import type { Translation } from '../messages';

export const COUNTY_EXPLORER_MESSAGES = {
  'counties.map.open': { en: 'Open {county}', sw: 'Fungua {county}', plain: 'Open {county}' },
} as const satisfies Record<string, Translation>;
