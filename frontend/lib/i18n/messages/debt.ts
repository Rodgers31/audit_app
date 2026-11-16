import type { Translation } from '../messages';

export const DEBT_MESSAGES = {
  'debt.headline.label': {
    en: 'Owed by the national government',
    sw: 'Deni la serikali ya kitaifa',
    plain: 'Money the national government owes',
  },
  'debt.headline.amount_unavailable': {
    en: 'Debt total unavailable',
    sw: 'Jumla ya deni haipatikani',
    plain: 'The total amount owed is not available',
  },
  'debt.headline.date_unavailable': {
    en: 'Balance date unavailable',
    sw: 'Tarehe ya salio la deni haipatikani',
    plain: 'The date for this amount is not available',
  },
} as const satisfies Record<string, Translation>;
