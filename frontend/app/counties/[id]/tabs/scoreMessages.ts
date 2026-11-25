import type { Translation } from '@/lib/i18n/messages';

export const SCORE_MESSAGES = {
  heading: {
    en: 'How {county}’s audit score is worked out',
    sw: 'Jinsi alama ya ukaguzi ya {county} inavyokokotolewa',
    plain: 'How {county}’s audit score is worked out',
  },
  takeaway: {
    en: '{county}’s audit score: {start} minus {deductions} = {score}, grade {grade}.',
    sw: 'Alama ya ukaguzi ya {county}: {start} toa {deductions} = {score}, daraja {grade}.',
    plain: '{county}’s audit score: {start} minus {deductions} = {score}, grade {grade}.',
  },
  start: { en: 'Start', sw: 'Mwanzo', plain: 'Start' },
  start_chart: { en: 'Start', sw: 'Anza', plain: 'Start' },
  found: { en: 'Found', sw: 'Matokeo', plain: 'Found' },
  serious: { en: 'Serious', sw: 'Mazito', plain: 'Serious' },
  repeat: { en: 'Repeat', sw: 'Rudia', plain: 'Repeat' },
  flagged: { en: 'Flagged', sw: 'Ibuliwa', plain: 'Flagged' },
  spent: { en: 'Spent', sw: 'Matumizi', plain: 'Spent' },
  opinion: { en: 'Opinion', sw: 'Maoni', plain: 'Opinion' },
  deduction: { en: 'Step', sw: 'Hatua', plain: 'Step' },
  rule: { en: 'Points and rule', sw: 'Pointi na kanuni', plain: 'Points and rule' },
  hint: {
    en: 'Select a bar for its rule. Press Escape to clear.',
    sw: 'Chagua kipau ili kusoma kanuni yake. Bonyeza Escape ili kufuta chaguo.',
    plain: 'Select a bar to see its rule. Press Escape to clear.',
  },
  remaining: {
    en: '{points} left out of {start} points',
    sw: 'Pointi {points} zimesalia kati ya {start}',
    plain: '{points} of {start} points left',
  },
} as const satisfies Record<string, Translation>;
