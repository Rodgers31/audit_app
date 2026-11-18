'use client';

import InfoSheet from '@/components/ui/InfoSheet';
import { evidenceUrl, qualificationMessageKey } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';
import { hasAmount, isTotal, revenuePublisher, sourceLocator, withheldResidual, type RevFy, type RevSource } from './RevenueMix.data';

const STATUS_LABELS = {
  'evidence.status.verified': 'foundation.verified',
  'evidence.status.qualified': 'foundation.qualified',
  'evidence.status.conflicting': 'foundation.conflicting',
  'evidence.status.unavailable': 'foundation.unavailable',
} as const;

function statuses(row: RevSource) {
  const keys = Object.values(row.qualifications ?? {}).map(qualificationMessageKey);
  return keys.length ? keys : [sourceLocator(row.source) ? 'evidence.status.qualified' as const : 'evidence.status.unavailable' as const];
}

const recorded = (text: unknown) => typeof text === 'string' && text.trim() ? text.trim() : null;

export default function RevenueSourceSheet({ latest, releases, label, basis, exact }: {
  latest: RevFy;
  releases: RevFy[];
  label: (row: RevSource) => string;
  basis: (row: RevSource) => string;
  exact: (amount: number) => string;
}) {
  const { t } = useLang();
  const amounts = latest.sources.filter(hasAmount).filter(row => row.basis !== 'projected');
  const current = amounts.filter(row => !isTotal(row));
  const totals = amounts.filter(isTotal);
  const creditRows = current.length ? current : totals;
  const publishers = new Set(creditRows.map(revenuePublisher));
  const versions = new Set(creditRows.map(row => row.source?.version));
  const publisher = publishers.size === 1 && creditRows.every(row => row.basis === 'published')
    ? Array.from(publishers)[0] : null;
  const displayPublisher = publisher === 'KRA' && versions.size === 1 && versions.has('dashboard_bundle')
    ? t('budget.revenue.kra_dashboard') : publisher;
  const chip = displayPublisher ? t('foundation.source').replace('{publisher}', () => displayPublisher) : t('foundation.sources');
  const currentStatuses = new Set(creditRows.flatMap(statuses));
  const dot = currentStatuses.size === 1 && currentStatuses.has('evidence.status.verified') ? 'bg-signal-good'
    : currentStatuses.has('evidence.status.qualified') || currentStatuses.has('evidence.status.conflicting')
      ? 'bg-signal-caution' : 'bg-neutral-muted';
  const links = new Set(creditRows.flatMap(row => {
    const link = evidenceUrl(row.source?.url) ?? sourceLocator(row.source);
    return link ? [link] : [];
  }));
  const sourceLinkClass = 'inline-flex min-h-11 max-w-full items-center break-words underline underline-offset-2';

  return (
    <div data-figure-evidence='revenue observations by period' className='min-w-0'>
      <InfoSheet title={t('budget.revenue.sources_title')} trigger={props => (
        <button {...props} type='button' className='audit-receipt rounded-full bg-surface-sunken px-3 text-left no-underline'
          data-testid='revenue-section-source'
          aria-label={displayPublisher ? chip : `${chip} · ${t('budget.revenue.title')}`}
          onClick={event => { event.currentTarget.focus(); props.onClick(); }}>
          <span className={`h-2 w-2 shrink-0 rounded-full ${dot}`} aria-hidden='true' />
          <span className='min-w-0 break-words'>{chip}</span>
        </button>
      )}>
        <p>{t('budget.revenue.collections_note')}</p>
        <ul className='space-y-1 border-y border-neutral-border py-2'>
          {Array.from(currentStatuses, status => <li key={status}>{t(STATUS_LABELS[status as keyof typeof STATUS_LABELS] ?? status)}</li>)}
        </ul>
        {Array.from(links, (link, index) => <a key={link} href={link} className={sourceLinkClass}>
          {t('evidence.open_source')}{links.size > 1 ? ` (${index + 1})` : ''}
        </a>)}
        {totals.length > 0 && (
          <div>
            <h3 className='font-semibold'>{t('budget.revenue.publisher_totals')}</h3>
            <dl className='space-y-1'>
              {totals.map(row => (
                <div key={row.revenue_type}>
                  <dt>{label(row)}</dt>
                  <dd>{exact(row.amount)} · {basis(row)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        <details>
          <summary className='min-h-11 cursor-pointer py-3 font-semibold'>{t('foundation.technical_details')}</summary>
          <p>{t('budget.revenue.history_note')}</p>
          {[...releases].reverse().map(release => (
            <section key={release.fiscal_year} aria-label={release.fiscal_year} className='space-y-2 border-b border-neutral-border py-2'>
              <h3 className='font-semibold'>{release.fiscal_year}</h3>
              {release.sources.map(row => {
                const source = row.source;
                const url = sourceLocator(source);
                const version = recorded(source?.version);
                const period = recorded(source?.period);
                const publication = recorded(source?.publication_date);
                const retrieved = recorded(source?.retrieved_at);
                const stated = withheldResidual(row) ? null : recorded(source?.stated_amount_billion_kes);
                const reconciliation = recorded(source?.reconciliation);
                return (
                  <div data-revenue-observation={row.revenue_type} data-basis={row.basis ?? undefined}
                    key={row.revenue_type} className='space-y-1 border-t border-neutral-border py-2'>
                    <p className='font-semibold'>{label(row)} · {hasAmount(row) ? exact(row.amount) : t('foundation.no_chart_value')} · {basis(row)}</p>
                    {row.absent_reason && <p>{row.absent_reason}</p>}
                    {row.basis && !withheldResidual(row) && row.basis_note && <p>{row.basis_note}</p>}
                    {url ? <a className={sourceLinkClass} href={url}>{t('budget.revenue.source_version')}</a>
                      : <p>{row.source_absent_reason || t('budget.revenue.url_unavailable')}</p>}
                    {version && <p>{t('budget.revenue.edition').replace('{value}', () => version)}</p>}
                    {period && <p>{t('budget.revenue.source_period').replace('{value}', () => period)}</p>}
                    {stated && <p>{t('budget.revenue.stated').replace('{value}', () => stated)}</p>}
                    {retrieved && <p>{t('budget.revenue.retrieved').replace('{value}', () => retrieved.slice(0, 10))}</p>}
                    {source && <p>{publication ? t('budget.revenue.published_on').replace('{value}', () => publication.slice(0, 10))
                      : t('budget.revenue.publication_unavailable')}</p>}
                    {reconciliation && <p>{reconciliation}</p>}
                    {Object.entries(row.qualifications ?? {}).map(([measure, qualification]) => {
                      const link = evidenceUrl(qualification?.source_url);
                      return (
                        <div key={measure} className='break-words'>
                          <p>{measure.replace(/_/g, ' ')} · {t(qualificationMessageKey(qualification))}</p>
                          {qualification?.identity && <p>{[
                            qualification.identity.geography, qualification.identity.period, qualification.identity.unit,
                            qualification.identity.basis, JSON.stringify(qualification.identity.dimensions),
                          ].filter(Boolean).join(' · ')}</p>}
                          {qualification?.reason && <p>{qualification.reason.replace(/_/g, ' ')}</p>}
                          {qualification?.publisher && <p>{qualification.publisher} · {qualification.source_kind}</p>}
                          <p>{t('evidence.bytes')}: {t(qualification?.document_bytes_checked ? 'evidence.checked' : 'evidence.not_checked')}
                            {' · '}{t('evidence.value')}: {t(qualification?.value_checked ? 'evidence.matched' : 'evidence.not_checked')}</p>
                          {link && link !== url && <a href={link} className={sourceLinkClass}>{t('evidence.open_source')}</a>}
                          {qualification?.locator && <p>{t('evidence.locator')}: {JSON.stringify(qualification.locator)}</p>}
                          {qualification?.digest && <p className='break-all'>{t('evidence.digest')}: {qualification.digest}</p>}
                        </div>
                      );
                    })}
                  </div>
                );
              })}
            </section>
          ))}
        </details>
      </InfoSheet>
    </div>
  );
}
