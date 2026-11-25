import type { FiscalYearData } from '@/lib/api/fiscal';
import type { QuizQuestion } from '@/data/quizData';
import { computeRevenueAllocation, formatHeadlineKes } from '@/lib/debt/revenueAllocation';
import { evidenceUrl } from '@/lib/evidence/qualification';
import type { Lang } from '@/lib/i18n/messages';
import { learnCopy } from '@/lib/i18n/messages/learn';

export interface QuizDebtQuestion extends QuizQuestion {
  language: 'en' | 'sw';
  context: string;
  sourceUrl: string;
}

export const LIVE_DEBT_QUESTION_ID = 'fin-debt-live';

const vintageLabels = {
  Actual: 'quizDebtActual',
  Preliminary: 'quizDebtPreliminary',
  Approved: 'quizDebtApproved',
  'Supplementary I': 'quizDebtSupplementary',
} as const;

const fiscalYear = (value: string | undefined) =>
  typeof value === 'string' ? value.match(/^(?:FY\s*)?(\d{4}\/\d{2})$/)?.[1] : undefined;

export function quizDebtQuestion(current: FiscalYearData | null | undefined, lang: Lang): QuizDebtQuestion | undefined {
  if (current?.unit !== 'KES') return;

  const allocation = computeRevenueAllocation(current);
  const service = current.measure_qualifications?.debt_service_cost;
  const revenue = current.measure_qualifications?.total_revenue;
  const year = fiscalYear(current.fiscal_year);
  if (!allocation || !year || !service || !revenue || !Object.hasOwn(vintageLabels, service.vintage)) return;

  const { rev, ds, debtServicePerRev } = allocation;
  const sourceUrl = evidenceUrl(service.source?.url);
  const digest = service.source?.sha256;
  if (!Number.isFinite(rev) || !Number.isFinite(ds) || ds < 0 ||
    service.value_kes !== ds || revenue.value_kes !== rev ||
    fiscalYear(service.fiscal_year) !== year || fiscalYear(revenue.fiscal_year) !== year ||
    service.basis !== 'total_debt_service_interest_and_principal' || revenue.basis !== 'ordinary_revenue_excl_aia' ||
    service.vintage !== revenue.vintage || !digest || !/^[0-9a-f]{64}$/.test(digest) ||
    digest !== revenue.source?.sha256 || !sourceUrl?.startsWith('https://')) return;

  // The fiscal API rounds its published KES-per-100 ratio to one decimal place.
  if (Math.abs((ds / rev) * 100 - debtServicePerRev) > 0.0500000001) return;

  const amount = formatHeadlineKes(debtServicePerRev);
  const options = [25, 50, 95, 100].filter(option => option !== amount).slice(0, 3);
  options.push(amount);
  options.sort((a, b) => a - b);

  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const whole = new Intl.NumberFormat(locale);
  const compact = new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 2 });
  const vintageLabel = vintageLabels[service.vintage as keyof typeof vintageLabels];
  return {
    id: LIVE_DEBT_QUESTION_ID,
    difficulty: 'medium',
    question: learnCopy(lang, 'quizDebtQuestion'),
    options: options.map(option => `KES ${whole.format(option)}`),
    correctIndex: options.indexOf(amount),
    explanation: learnCopy(lang, 'quizDebtExplanation', {
      year, service: compact.format(ds), revenue: compact.format(rev),
    }),
    language: lang === 'sw' ? 'sw' : 'en',
    context: learnCopy(lang, vintageLabel, { year }),
    sourceUrl,
  };
}
