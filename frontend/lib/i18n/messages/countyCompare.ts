import type { Translation } from '../messages';

export const COUNTY_COMPARE_MESSAGES = {
  placeholder: {
    en: 'Search county',
    sw: 'Tafuta kaunti',
    plain: 'Find a county',
  },
  add: {
    en: 'Add a county',
    sw: 'Ongeza kaunti',
    plain: 'Add a county',
  },
  suggestions: {
    en: 'Suggested pairs',
    sw: 'Jozi za kaunti zinazopendekezwa',
    plain: 'Try these counties',
  },
  pair: {
    en: '{first} vs {second}',
    sw: '{first} na {second}',
    plain: '{first} and {second}',
  },
  clear: {
    en: 'Clear county',
    sw: 'Ondoa chaguo',
    plain: 'Clear this county',
  },
  noMatches: {
    en: 'No counties match.',
    sw: 'Hakuna kaunti zinazolingana.',
    plain: 'No counties found.',
  },
  readingNote: {
    en: 'Green marks the best value in each row and red the worst. Higher is usually better. For pending bills and debt, lower is better. Tap or select a county name to open its page.',
    sw: 'Kijani kinaonyesha thamani bora katika kila safu na nyekundu inaonyesha mbaya zaidi. Kwa kawaida thamani ya juu ni bora. Kwa ankara zilizokwama na deni, thamani ya chini ni bora. Gusa au chagua jina la kaunti ili kufungua ukurasa wake.',
    plain: 'Green shows the best number and red the worst in each row. Higher is usually better. For unpaid bills and debt, lower is better. Tap or select a county name to open its page.',
  },
} as const satisfies Record<string, Translation>;
