import type { Translation } from '../messages';

export const COUNTY_EXPLORER_MESSAGES = {
  'counties.rankings.show_all_count': { en: 'Show all {count} counties', sw: 'Onyesha kaunti zote {count}', plain: 'Show all {count} counties' },
  'counties.rankings.rank': { en: 'Rank', sw: 'Nafasi', plain: 'Rank' },
  'counties.rankings.spending_period': { en: 'Spending rate · {period}', sw: 'Kiwango cha matumizi · {period}', plain: 'Share of budget spent · {period}' },
  'counties.rankings.below_target': { en: 'Below the 70% target', sw: 'Chini ya lengo la 70%', plain: 'Below the 70% goal' },
  'counties.rankings.measure_unavailable': { en: 'Not published', sw: 'Haijachapishwa', plain: 'Not published' },
  'counties.rankings.modelled_amount': { en: 'Modelled estimate', sw: 'Makadirio ya modeli', plain: 'Estimated from a model' },
  'counties.rankings.compare': { en: 'Compare', sw: 'Linganisha', plain: 'Compare' },
  'counties.rankings.compare_county': { en: 'Compare {county}', sw: 'Linganisha {county}', plain: 'Compare {county}' },
  'counties.rankings.compare_selection': { en: 'Selected counties for comparison', sw: 'Kaunti zilizochaguliwa kulinganishwa', plain: 'Counties to compare' },
  'counties.rankings.compare_selected': { en: '{count} selected', sw: '{count} zimechaguliwa', plain: '{count} selected' },
  'counties.rankings.compare_limit': { en: 'Up to {count} counties can be compared.', sw: 'Unaweza kulinganisha hadi kaunti {count}.', plain: 'Compare up to {count} counties.' },
  'counties.rankings.health_explanation': { en: 'Explain {county} financial health grade {grade}', sw: 'Eleza daraja {grade} la afya ya kifedha ya {county}', plain: 'Explain the money health grade {grade} for {county}' },
  'counties.map.open': { en: 'Open {county}', sw: 'Fungua {county}', plain: 'Open {county}' },
} as const satisfies Record<string, Translation>;
