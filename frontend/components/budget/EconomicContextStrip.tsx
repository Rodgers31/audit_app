'use client';

import FigureEvidence from '@/components/evidence/FigureEvidence';
import StatCard from '@/components/ui/StatCard';
import { evidenceUrl, qualificationMessageKey, type FigureQualification, type Qualifications } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { ArrowUpRight } from 'lucide-react';
import { useId } from 'react';

interface EconomicContext {
  qualifications?: {
    gdp?: Qualifications;
    gdp_growth?: Qualifications;
    inflation?: Qualifications;
  };
  gdp_billion_kes?: number | null;
  gdp_as_of?: string | null;
  gdp_growth_pct?: number | null;
  gdp_growth_as_of?: string | null;
  inflation_pct?: number | null;
  inflation_as_of?: string | null;
  inflation_measure?: string | null;
  // Older deployments can supply this without a compatible fiscal-year denominator.
  budget_to_gdp_pct?: number | null;
  revenue_to_gdp_pct?: number | null;
}

const CBK_INFLATION = 'https://www.centralbank.go.ke/inflation-rates/';
const CBK_TARGETS = [
  {
    start: '2024-07', end: '2026-06', lower: 2.5, upper: 7.5,
    publication: 'budget.context.cbk_report', page: '13',
    url: 'https://www.centralbank.go.ke/uploads/monetary_policy_reports/131378250_36th%20Monetary%20Policy%20Committee%20Report%2C%20April%202026.pdf#page=20',
  },
  {
    start: '2026-07', end: '2027-06', lower: 2.5, upper: 7.5,
    publication: 'budget.context.cbk_statement', page: '18',
    url: 'https://www.centralbank.go.ke/uploads/monetary_policy_statements/366885193_58th%20Monetary%20Policy%20Statement%2C%20June%202026.pdf#page=25',
  },
] as const;

function finite(value?: number | null): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

/** Keep the reporting date in UTC even when the API sends a timezone-less midnight. */
function observationDate(value?: string | null): Date | null {
  if (!value || !/^\d{4}-\d{2}-\d{2}(?:T.+)?$/.test(value) || !Number.isFinite(Date.parse(value))) return null;
  const day = value.slice(0, 10);
  const date = new Date(`${day}T00:00:00Z`);
  return Number.isFinite(date.getTime()) && date.toISOString().startsWith(day) ? date : null;
}

function nationalObservation(q: FigureQualification | undefined, measure: string, period: string, unit: string) {
  const identity = q?.identity;
  return identity?.entity_id === null && identity.geography === 'KEN' && identity.measure === measure &&
    identity.period === period && identity.unit === unit && identity.basis === 'actual';
}

function sourcedAnnualValue(q: FigureQualification | undefined, measure: string, year: string, unit: string) {
  const status = qualificationMessageKey(q);
  return !!year && nationalObservation(q, measure, year, unit) && !!evidenceUrl(q?.source_url) &&
    (status === 'evidence.status.verified' || status === 'evidence.status.qualified');
}

function applicableBand(q: FigureQualification | undefined, month: string, measure?: string | null) {
  if (measure !== '12-month CPI inflation' || !nationalObservation(q, 'inflation_rate_12m', month, 'percent') ||
      qualificationMessageKey(q) !== 'evidence.status.verified' || q?.source_kind !== 'web' ||
      q.publisher !== 'Central Bank of Kenya' || evidenceUrl(q.source_url) !== CBK_INFLATION) return undefined;
  return CBK_TARGETS.find(band => month >= band.start && month <= band.end);
}

export default function EconomicContextStrip({ ctx }: { ctx: EconomicContext | null | undefined }) {
  const { lang, t } = useLang();
  const headingId = useId();
  if (!ctx) return null;

  const locale = lang === 'sw' ? 'sw-KE' : 'en-KE';
  const pct = (value: number) =>
    `${value.toLocaleString(locale, { minimumFractionDigits: 1, maximumFractionDigits: 2 })}%`;
  const gdpYear = observationDate(ctx.gdp_as_of)?.toISOString().slice(0, 4) ?? '';
  const growthYear = observationDate(ctx.gdp_growth_as_of)?.toISOString().slice(0, 4) ?? '';
  const gdp = finite(ctx.gdp_billion_kes) && ctx.gdp_billion_kes >= 0 &&
    sourcedAnnualValue(ctx.qualifications?.gdp?.total_national_gdp, 'total_national_gdp', gdpYear, 'KES_millions')
    ? ctx.gdp_billion_kes : null;
  const growth = finite(ctx.gdp_growth_pct) &&
    sourcedAnnualValue(ctx.qualifications?.gdp_growth?.gdp_growth_rate, 'gdp_growth_rate', growthYear, 'percent')
    ? t('budget.context.growth').replace('{year}', growthYear).replace('{value}', pct(ctx.gdp_growth_pct)) : null;
  const gdpValue = gdp == null ? null : `KES ${gdp >= 1000 ? `${(gdp / 1000).toFixed(2)}T` : `${gdp.toFixed(0)}B`}`;
  const nominalPeriod = gdp == null ? null : t('budget.context.gdp_period').replace('{year}', gdpYear);
  const exactGdp = gdp == null ? null : t('budget.context.gdp_exact')
    .replace('{value}', `KES ${Math.round(gdp * 1e9).toLocaleString(locale)}`).replace('{year}', gdpYear);

  const inflation = finite(ctx.inflation_pct) ? ctx.inflation_pct : null;
  const inflationDate = observationDate(ctx.inflation_as_of);
  const month = inflationDate?.toISOString().slice(0, 7) ?? '';
  const measure = ctx.inflation_measure === '12-month CPI inflation' ? t('budget.context.monthly_cpi')
    : ctx.inflation_measure === 'CPI inflation, annual average' ? t('budget.context.annual_cpi') : ctx.inflation_measure;
  const inflationPeriod = inflationDate?.toLocaleDateString(locale, {
    year: 'numeric', ...(ctx.inflation_measure === 'CPI inflation, annual average' ? {} : { month: 'long' }), timeZone: 'UTC',
  });
  const inflationBasis = [measure, inflationPeriod].filter(Boolean).join(' · ');
  const band = inflation == null ? undefined : applicableBand(ctx.qualifications?.inflation?.inflation_rate_12m, month, ctx.inflation_measure);
  const caution = band && inflation != null && (inflation < band.lower || inflation > band.upper)
    ? t(inflation < band.lower ? 'budget.context.below_target' : 'budget.context.above_target') : null;
  const target = band && t('budget.context.target').replace('{lower}', String(band.lower)).replace('{upper}', String(band.upper));
  const citation = band && t('budget.context.cbk_citation').replace('{publication}', t(band.publication)).replace('{page}', band.page);
  const ratioReason = t('budget.context.ratio_reason');

  return (
    <section aria-labelledby={headingId} className='space-y-3' onClickCapture={event => {
      // Safari may open a dialog by touch without focusing its trigger (#1013).
      if (event.target instanceof Element) {
        event.target.closest<HTMLButtonElement>('button[aria-haspopup="dialog"]')?.focus({ preventScroll: true });
      }
    }}>
      <h2 id={headingId} className='font-display text-audit-heading font-semibold text-neutral-text'>{t('budget.context.title')}</h2>
      <div className='grid gap-3 md:grid-cols-3'>
        <StatCard label={t('budget.context.gdp')} value={gdpValue}
          comparison={nominalPeriod || growth ? <>{nominalPeriod && <span className='block'>{nominalPeriod}</span>}{growth && <span className='block'>{growth}</span>}</> : undefined}
          source={<FigureEvidence label='GDP' labelKey='evidence.label.gdp'
            qualifications={{ ...ctx.qualifications?.gdp, ...ctx.qualifications?.gdp_growth }} explanation={exactGdp ?? undefined} />}
        />
        <StatCard label={t('budget.context.ratio')} value={null} comparison={ratioReason}
          source={<FigureEvidence label='Budget / GDP' labelKey='evidence.label.budget_gdp' explanation={ratioReason} />}
        />
        <StatCard label={t('budget.context.inflation')} value={inflation == null ? null : pct(inflation)}
          comparison={inflation == null ? undefined : inflationBasis || t('budget.context.inflation_basis_missing')}
          verdict={caution && target ? { signal: 'caution', word: caution, rule: target, details: null } : undefined}
          source={<>
            <FigureEvidence label='Inflation' labelKey='evidence.label.inflation' qualifications={ctx.qualifications?.inflation} />
            {band && <a href={band.url} target='_blank' rel='noopener noreferrer' className='audit-receipt text-left'>
              <span className='min-w-0 break-words'>{!caution && <span className='block'>{target}</span>}{citation}</span>
              <ArrowUpRight size={15} aria-hidden='true' className='shrink-0' />
            </a>}
          </>}
        />
      </div>
    </section>
  );
}
