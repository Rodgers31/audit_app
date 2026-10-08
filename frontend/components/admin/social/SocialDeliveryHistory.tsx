'use client';

import { SocialAccount, SocialHistoricalTarget } from '@/lib/api/social';
import { useSocialHistory } from '@/lib/hooks/useSocial';
import { useState } from 'react';
import { SocialErrorBanner } from './SocialNotice';
import { httpsUrl, platformLabels } from './socialDocument';
import styles from './social.module.css';

export default function SocialDeliveryHistory({ postId, preview, count, accounts }: { postId: string; preview: SocialHistoricalTarget[]; count: number; accounts: SocialAccount[] }) {
  const [inspected, setInspected] = useState(false);
  const [page, setPage] = useState(1);
  const history = useSocialHistory(postId, page, inspected);
  const targets = inspected ? history.data?.targets ?? [] : preview;
  const total = inspected ? history.data?.total ?? count : count;
  return <section aria-label='Delivery history' className={styles.fields}>
    <div><h3>Delivery history</h3><p className={styles.muted}>{total} historical deliveries. Each receipt belongs to its own reviewed revision; current draft actions use the current authorization.</p></div>
    {history.error && <SocialErrorBanner error={history.error} onRetry={() => history.refetch()} />}
    {inspected && history.isPending && <p role='status'>Loading delivery history…</p>}
    {targets.map(target => {
      const url = target.state === 'published' ? httpsUrl(target.remote_url) : undefined;
      return <article key={target.id} className={styles.result} aria-label={`${platformLabels[target.platform]} historical delivery`}>
        <div className={styles.resultHeader}><strong>{platformLabels[target.platform]} · {accounts.find(a => a.id === target.account_id)?.display_name ?? target.account_id}</strong><span className={styles.badge}>{target.state.replaceAll('_', ' ')}</span></div>
        <p className={styles.muted}>Reviewed revision {target.revision_id} · authorization {target.publication_id}</p>
        <p className={styles.muted}>Approved by {target.approved_by} at {target.approved_at} (UTC)</p>
        {target.scheduled_for && <p className={styles.muted}>Original due time: {target.scheduled_for} (UTC)</p>}
        <p className={styles.muted}>Delivery updated: {target.updated_at} (UTC)</p>
        {target.cancel_requested_at && <p className={styles.muted}>Cancellation requested: {target.cancel_requested_at} (UTC)</p>}
        {target.revoked_at && <p className={styles.muted}>Authorization revoked: {target.revoked_at} (UTC)</p>}
        {target.safe_error_message && <p>{target.safe_error_message}</p>}
        {target.published_at && <p className={styles.muted}>Confirmed publication: {target.published_at} (UTC)</p>}
        {url && <a href={url} target='_blank' rel='noopener noreferrer'>View historical {platformLabels[target.platform]} post</a>}
        {['outcome_unknown', 'reconciling'].includes(target.state) && <p className={styles.notice}>The platform may have accepted this delivery. Reconciliation is required.</p>}
      </article>;
    })}
    {!inspected && count > 20 && <button type='button' className={styles.button} onClick={() => setInspected(true)}>Inspect all delivery history</button>}
    {inspected && history.data && <div className={styles.pagination}>
      <button type='button' className={styles.button} disabled={page === 1 || history.isFetching} onClick={() => setPage(page - 1)}>Previous history page</button>
      <span className={styles.muted}>Delivery history page {page} of {Math.max(1, Math.ceil(total / 20))}</span>
      <button type='button' className={styles.button} disabled={!history.data.has_more || history.isFetching} onClick={() => setPage(page + 1)}>Next history page</button>
      <button type='button' className={styles.button} disabled={history.isFetching} onClick={() => history.refetch()}>Refresh delivery history</button>
    </div>}
  </section>;
}
