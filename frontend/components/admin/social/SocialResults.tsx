'use client';

import { decodePost, SocialAccount, SocialTarget } from '@/lib/api/social';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { useState } from 'react';
import { SocialErrorBanner } from './SocialNotice';
import { httpsUrl, platformLabels } from './socialDocument';
import styles from './social.module.css';

export default function SocialResults({ targets, accounts, postId }: { targets: SocialTarget[]; accounts: SocialAccount[]; postId: string }) {
  const mutation = useSocialMutation();
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [message, setMessage] = useState('');
  async function retry(id: string) {
    setMessage('');
    try {
      await mutation.run(`/targets/${encodeURIComponent(id)}/retry`, { reason: reasons[id] }, decodePost, { postId });
      setMessage('Retry command accepted. Delivery is confirmed only by the updated destination result.');
    } catch { /* The typed mutation banner retains the failure. */ }
  }
  return <section aria-label='Delivery results' className={styles.fields}>
    <div><h3>Delivery results</h3><p className={styles.muted}>Each account has its own outcome. Queued means accepted for dispatch; it does not mean published.</p></div>
    {mutation.error && <SocialErrorBanner error={mutation.error} />}
    {message && <p className={styles.success} role='status'>{message}</p>}
    {!targets.length && <p className={styles.empty}>No publication results yet.</p>}
    {targets.map(target => {
      const account = accounts.find(a => a.id === target.account_id);
      const url = target.state === 'published' ? httpsUrl(target.remote_url) : undefined;
      const ambiguous = ['outcome_unknown', 'reconciling'].includes(target.state);
      return <article key={target.id} className={styles.result} aria-label={`${platformLabels[target.platform]} delivery`}>
        <div className={styles.resultHeader}><strong>{platformLabels[target.platform]} · {account?.display_name ?? 'Account identity unavailable'}</strong><span className={styles.badge}>{target.state.replaceAll('_', ' ')}</span></div>
        {target.safe_error_message && <p>{target.safe_error_message}</p>}
        {target.next_action_at && <p className={styles.muted}>Next action: {target.next_action_at} (UTC)</p>}
        {target.published_at && <p className={styles.muted}>Confirmed publication: {target.published_at} (UTC)</p>}
        {url ? <a href={url} target='_blank' rel='noopener noreferrer'>View {platformLabels[target.platform]} post</a> : target.state === 'published' && <p className={styles.muted}>Published; a verified HTTPS post link is unavailable.</p>}
        {ambiguous && <p className={styles.notice}>The platform may have accepted this post. Reconciliation is required; another send is unavailable.</p>}
        {target.state === 'failed' && <div className={styles.fields}><label htmlFor={`retry-${target.id}`}>Reason to retry {platformLabels[target.platform]}<input id={`retry-${target.id}`} value={reasons[target.id] ?? ''} onChange={e => setReasons({ ...reasons, [target.id]: e.target.value })} /></label><button className={styles.button} type='button' disabled={mutation.isPending || !reasons[target.id]?.trim()} onClick={() => retry(target.id)}>Request safe retry for {platformLabels[target.platform]}</button><p className={styles.muted}>The server checks retry eligibility. Other destinations keep their existing results.</p></div>}
      </article>;
    })}
  </section>;
}
