import type { Translation } from '../messages';

export const COUNTY_EXPLORER_MESSAGES = {
  'counties.map.open': { en: 'Open {county}', sw: 'Fungua {county}', plain: 'Open {county}' },
} as const satisfies Record<string, Translation>;

export const COUNTY_PIN_MESSAGES = {
  label: { en: 'Your county', sw: 'Kaunti yako', plain: 'Your county' },
  spent: { en: '{rate}% spent', sw: '{rate}% imetumika', plain: '{rate}% of budget spent' },
} as const satisfies Record<string, Translation>;
