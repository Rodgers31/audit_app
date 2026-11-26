'use client';

import InfoTip from '@/components/InfoTip';
import FigureEvidence from '@/components/evidence/FigureEvidence';
import type { DebtTimelineEntry } from '@/lib/api/debt';
import { formatAsAt } from '@/lib/counties/pendingBillsNotes';
import { publishedHeadlineRatio } from '@/lib/debt/qualification';
import { evidenceUrl } from '@/lib/evidence/qualification';
import { useLang } from '@/lib/i18n/LangProvider';

const imfSeriesUrl = 'https://www.imf.org/external/datamapper/GGXWDG_NGDP@WEO/KEN';

type Snapshot = {
  debt_to_gdp_year?: number;
  debt_to_gdp_source?: string;
  debt_to_gdp_vintage?: string;
  debt_to_gdp_observation?: DebtTimelineEntry;
  figure_qualifications?: { derived_ratio?: { status: string; reason: string } };
};

export default function DebtGdpContext({ data }: { data: unknown }) {
  const { lang, t } = useLang();
  const ratio = publishedHeadlineRatio(data);
  const snapshot = ratio == null ? null : data as Snapshot;
  const imf = snapshot?.debt_to_gdp_source === 'IMF World Economic Outlook';
  const observation = imf ? undefined : snapshot?.debt_to_gdp_observation;
  const stockSource = evidenceUrl(observation?.qualifications?.total?.source_url);
  const gdpSource = evidenceUrl(observation?.qualifications?.gdp?.source_url);
  const vintage = snapshot?.debt_to_gdp_vintage;
  const snapshotDay = typeof vintage === 'string'
    && /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?$/.test(vintage)
    && Number.isFinite(Date.parse(vintage)) ? vintage.slice(0, 10) : null;
  const snapshotDate = formatAsAt(snapshotDay, lang);

  return (
    <section id='debt-to-gdp' aria-labelledby='debt-to-gdp-title' className='min-w-0 space-y-2 border-t border-neutral-border pt-4'>
      <div className='flex flex-wrap items-center gap-1'>
        <h2 id='debt-to-gdp-title' className='font-display text-2xl sm:text-3xl'>{t('debt.gdp.title')}</h2>
        <InfoTip term='debt-to-gdp' className='[&>button]:min-h-11 [&>button]:min-w-11' />
      </div>
      {ratio == null ? (
        <p className='text-sm text-neutral-muted'>{t('debt.gdp.unavailable')}</p>
      ) : (
        <>
          <p className='audit-figure text-4xl text-neutral-text'>{ratio.toFixed(1)}%</p>
          <p className='text-sm text-neutral-muted'>{t(imf ? 'debt.gdp.imf_basis' : 'debt.gdp.cbk_basis')}</p>
          <p className='text-sm text-neutral-muted'>
            {t('debt.gdp.year').replace('{year}', String(snapshot?.debt_to_gdp_year))}
            {' · '}
            {imf
              ? snapshotDate
                ? t('debt.gdp.snapshot_date').replace('{date}', snapshotDate)
                : t('debt.gdp.snapshot_date_missing')
              : t('debt.gdp.stock_month').replace('{month}', observation?.period?.stock_as_of_month ?? '')}
          </p>
          <ul className='flex flex-wrap gap-x-4 gap-y-1'>
            {imf ? (
              <li><a className='audit-receipt break-words' href={imfSeriesUrl} target='_blank' rel='noopener noreferrer'>{t('debt.gdp.imf_source')}</a></li>
            ) : (
              <>
                {stockSource && <li><a className='audit-receipt break-words' href={stockSource} target='_blank' rel='noopener noreferrer'>{t('debt.gdp.cbk_source')}</a></li>}
                {gdpSource && <li><a className='audit-receipt break-words' href={gdpSource} target='_blank' rel='noopener noreferrer'>{t('debt.gdp.wb_source')}</a></li>}
              </>
            )}
          </ul>
          <p className='text-sm text-neutral-muted'>{t('debt.gdp.history_unavailable')}</p>
          <FigureEvidence label='published debt-to-GDP ratio' labelKey='evidence.label.published_debt_ratio'
            note={snapshot?.figure_qualifications?.derived_ratio} qualifications={observation?.qualifications} />
        </>
      )}
    </section>
  );
}
