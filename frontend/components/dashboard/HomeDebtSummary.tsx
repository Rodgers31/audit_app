'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import StatCard from '@/components/ui/StatCard';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { dsaCitation, dsaIsAlarm, dsaSourceLabel } from '@/lib/debt/dsaRating';
import { evidenceUrl, qualificationMessageKey } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { HOME_DEBT_SUMMARY } from '@/lib/i18n/messages/homeDebtSummary';
import { useDebtTimeline, useNationalDebtOverview } from '@/lib/react-query/useDebt';
import { fmtBillionKES } from '@/lib/utils';
import Link from 'next/link';
import type { ReactNode } from 'react';
import { homeDebtSummary } from './homeDebtFacts';

const WEO_SERIES = 'https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO/KEN';
const CBK = 'Central Bank of Kenya';
const LINK = 'flex min-h-11 items-center underline underline-offset-4 [overflow-wrap:anywhere]';

function SummarySource({ label, title, publisher, children }: {
  label: string; title: string; publisher: string; children: ReactNode;
}) {
  const { t } = useLang();
  const source = t('foundation.source').replace('{publisher}', () => publisher);
  return (
    <div data-figure-evidence={label}>
      <InfoSheet title={title} trigger={props => (
        <button {...props} type='button' className='audit-receipt text-left'
          aria-label={`${source} · ${t('evidence.for').replace('{label}', () => title)}`}
          onClick={event => {
            event.currentTarget.focus({ preventScroll: true });
            props.onClick();
          }}>
          <span aria-hidden='true' className='size-2 shrink-0 bg-neutral-muted' />
          <span className='min-w-0 [overflow-wrap:anywhere]'>{source}</span>
        </button>
      )}>
        {children}
      </InfoSheet>
    </div>
  );
}

export default function HomeDebtSummary() {
  const { lang, t } = useLang();
  const { data: overview } = useNationalDebtOverview();
  const { data: timeline } = useDebtTimeline();
  const latest = timeline?.timeline?.at(-1);
  const { register, registerDate, rows, loanEvidence, stock, ratioValue, imf,
    ratioObservation, ratioStock, ratioYear, ratioVintage, dsa, dsaSource } = homeDebtSummary(overview, latest);
  const copy = (key: keyof typeof HOME_DEBT_SUMMARY, values: Record<string, string> = {}) =>
    HOME_DEBT_SUMMARY[key][lang].replace(/\{(\w+)\}/g, (token, name) => values[name] ?? token);
  const number = new Intl.NumberFormat(lang === 'sw' ? 'sw-KE' : 'en-KE');
  const money = (amount: number) => `KES ${amount >= 1e9 ? fmtBillionKES(amount / 1e9) : number.format(amount)}`;
  const exact = (amount: number) => copy('exactTotal', { amount: `KES ${number.format(amount)}` });
  const month = (stamp: string) => new Intl.DateTimeFormat(lang === 'sw' ? 'sw-KE' : 'en-GB', {
    month: 'long', year: 'numeric', timeZone: 'UTC',
  }).format(new Date((stamp.length === 7 ? stamp + '-01' : stamp) + 'T00:00:00Z'));
  const when = (stamp: string) => stamp.length === 7 ? month(stamp) : formatAsAt(stamp, lang) ?? stamp;
  const registerComparison = copy(rows == null ? 'registerUncounted' : 'registerComparison', { rows: number.format(rows ?? 0) });
  const coverage = registerDate ? copy('registerDate', { period: when(registerDate) }) : copy('registerUndated');
  const selectedDebt = register ?? stock?.value ?? null;
  const ratio = ratioValue?.toFixed(1);
  const cbkMonth = ratioObservation?.period?.stock_as_of_month;
  const ratioComparison = ratio != null && ratioYear != null && (imf || cbkMonth)
    ? copy(imf ? 'imfComparison' : 'cbkComparison', { rate: ratio, year: String(ratioYear), period: cbkMonth ? month(cbkMonth) : '' })
    : undefined;
  const ratioGdpLink = evidenceUrl(ratioObservation?.qualifications?.gdp?.source_url);
  const rating = dsa?.overall_risk_of_debt_distress.trim().toLowerCase();
  const alarm = dsaIsAlarm(dsa);
  const dsaValue = rating === 'high' ? copy('riskHigh') : rating === 'moderate' ? copy('riskModerate')
    : rating === 'low' ? copy('riskLow') : rating === 'in debt distress' ? copy('distressed')
      : dsa?.overall_risk_of_debt_distress ?? null;

  return (
    <section aria-label={copy('heading')} data-home-debt-summary
      className='grid min-w-0 gap-3 md:grid-cols-3 [&_.audit-panel]:h-full'>
      <div data-summary-debt>
        <StatCard label={copy(register == null ? 'stock' : 'register')} value={selectedDebt == null ? null : money(selectedDebt)}
          missingReason={copy('debtMissing')}
          comparison={register != null ? `${registerComparison} · ${coverage}`
            : stock ? copy('stockComparison', { period: month(stock.month) }) : null}
          source={selectedDebt != null && <SummarySource label='debt register operands'
            title={register != null ? t('evidence.label.debt_register') : copy('stock')}
            publisher={register != null ? copy('registerPublisher') : CBK}>
            <p>{exact(selectedDebt)}</p>
            {register != null && <p>{registerComparison} · {coverage}.</p>}
            {stock && (
              <>
                <p>{register == null ? copy('stockComparison', { period: month(stock.month) })
                  : copy('separateStock', { amount: `KES ${number.format(stock.value)}`, period: month(stock.month) })}</p>
                <a href={stock.href} target='_blank' rel='noopener noreferrer' className={LINK}>
                  {copy('stockLink')}{stock.table ? ` · ${stock.table}` : ''}
                </a>
              </>
            )}
            {loanEvidence.length > 0 && (
              <details className='border-y border-neutral-border'>
                <summary className='min-h-11 cursor-pointer py-2 font-semibold'>{copy('registerEvidence')}</summary>
                <ul>
                  {loanEvidence.map(({ id, proof }) => (
                    <li key={id}>
                      <Link className={LINK} href={`/sources/figures/loans/${id}`}>
                        {copy('record', { id })} · {t(qualificationMessageKey(proof))}
                      </Link>
                    </li>
                  ))}
                </ul>
              </details>
            )}
            <Link className={LINK} href='/debt'>{copy('debtPage')}</Link>
          </SummarySource>} />
      </div>
      <div data-summary-ratio>
        <StatCard label={copy('ratio')} value={ratio == null ? null : `${ratio}%`} missingReason={copy('ratioMissing')}
          comparison={ratioComparison}
          source={ratio != null && <SummarySource label='debt-to-GDP observation' title={t('evidence.label.debt_to_gdp')}
            publisher={imf ? 'IMF World Economic Outlook' : 'Central Bank of Kenya / World Bank'}>
            <p>{ratioComparison}</p>
            {imf ? (
              <>
                <p>{t('foundation.qualified')}</p>
                {ratioVintage && <p>{copy('imfVintage', { date: when(ratioVintage) })}</p>}
                <p>{copy('imfMethod')}</p>
                <a href={WEO_SERIES} target='_blank' rel='noopener noreferrer' className={LINK}>{copy('imfLiveSeries')}</a>
              </>
            ) : (
              <>
                {ratioStock && <a href={ratioStock.href} target='_blank' rel='noopener noreferrer' className={LINK}>{copy('stockLink')}</a>}
                {ratioGdpLink && <a href={ratioGdpLink} target='_blank' rel='noopener noreferrer' className={LINK}>{copy('gdpLink')}</a>}
              </>
            )}
          </SummarySource>} />
      </div>
      <div data-summary-dsa data-signal={alarm ? 'alarm' : 'context'}
        className={alarm ? '[&_.audit-figure]:text-signal-alarm' : undefined}>
        <StatCard label={copy('risk')} value={dsaValue} missingReason={t('home.hero.risk_unassessed_value')}
          comparison={dsa ? copy(dsa.freshness?.status === 'recent_confirmation' ? 'dsaComparisonRecent' : 'dsaComparison', { date: when(dsa.source.dsa_date) }) : null}
          source={dsa && dsaSource && <SummarySource label='debt distress assessment' title={copy('risk')} publisher={copy('dsaSources')}>
            <p>{copy('dsaOfficial', { value: dsa.overall_risk_of_debt_distress })}</p>
            {dsa.source.published && <p>{copy('dsaPublished', { date: when(dsa.source.published) })}</p>}
            {dsa.latest_confirmed && <p>{copy('dsaConfirmed', { date: when(dsa.latest_confirmed.as_of) })}</p>}
            <a href={dsaSource} title={dsaCitation(dsa)} target='_blank' rel='noopener noreferrer' className={LINK}>{dsaSourceLabel(dsa)}</a>
          </SummarySource>} />
      </div>
    </section>
  );
}
