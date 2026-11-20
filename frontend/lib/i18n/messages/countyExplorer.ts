import type { Translation } from '../messages';

export const COUNTY_EXPLORER_MESSAGES = {
  'counties.map.open': { en: 'Open {county}', sw: 'Fungua {county}', plain: 'Open {county}' },
  'counties.spending.measure': { en: 'Spending rate', sw: 'Kiwango cha matumizi', plain: 'Share of budget spent' },
  'counties.spending.map_title': { en: 'County spending map', sw: 'Ramani ya matumizi ya kaunti', plain: 'County spending map' },
  'counties.spending.view': { en: 'County view', sw: 'Mwonekano wa kaunti', plain: 'County view' },
  'counties.spending.list': { en: 'List', sw: 'Orodha', plain: 'List' },
  'counties.spending.map': { en: 'Map', sw: 'Ramani', plain: 'Map' },
  'counties.spending.legend': { en: 'Spending rate key', sw: 'Ufafanuzi wa viwango vya matumizi', plain: 'Spending rate key' },
  'counties.spending.target': { en: 'Annual target: {target}%', sw: 'Lengo la mwaka: {target}%', plain: 'Annual target: {target}%' },
  'counties.spending.above': { en: 'Above target', sw: 'Zaidi ya lengo', plain: 'Above target' },
  'counties.spending.on': { en: 'On target', sw: 'Lengo limefikiwa', plain: 'On target' },
  'counties.spending.below': { en: 'Below target', sw: 'Chini ya lengo', plain: 'Below target' },
  'counties.spending.well-below': { en: 'Well below target', sw: 'Chini sana ya lengo', plain: 'Well below target' },
  'counties.spending.reported': { en: 'Reported for this period', sw: 'Imeripotiwa kwa kipindi hiki', plain: 'Reported for this period' },
  'counties.spending.unavailable': { en: 'No published rate', sw: 'Kiwango hakijachapishwa', plain: 'No published rate' },
} as const satisfies Record<string, Translation>;
