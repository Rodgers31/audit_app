'use client';

import { decodePost, SocialApiError, SocialPost } from '@/lib/api/social';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { useRef, useState } from 'react';
import { SocialErrorBanner } from './SocialNotice';
import { draftFingerprint } from './socialDocument';
import styles from './social.module.css';

export default function SocialArchiveControls({ post, disabled, onUpdated, onBusyChange }: { onBusyChange: (active: boolean) => void; post: SocialPost; disabled: boolean; onUpdated: (post: SocialPost) => void }) {
  const mutation = useSocialMutation();
  const running = useRef(false);
  const [confirming, setConfirming] = useState(false);
  const archived = post.editorial_state === 'archived';
  const eligible = post.archive?.eligible === true && !archived;
  async function archive() {
    if (running.current || disabled || !eligible) return;
    running.current = true; onBusyChange(true);
    try {
      const result = await mutation.run(`/posts/${encodeURIComponent(post.id)}/archive`, { expected_version: post.version }, value => {
        const detail = decodePost(value);
        if (detail.id !== post.id || detail.version !== post.version + 1 || detail.editorial_state !== 'archived' || !detail.archive?.archived_at || detail.archive.eligible || detail.revision_id !== post.revision_id || draftFingerprint(detail) !== draftFingerprint(post)) throw new SocialApiError('INVALID_RESPONSE', 'The archive receipt did not confirm retained content and the next archived version. Refresh the revision; the original command key is preserved.');
        return detail;
      }, { postId: post.id });
      onUpdated(result); setConfirming(false);
    } catch { /* Typed error remains visible; retries retain the command key. */ }
    finally { running.current = false; onBusyChange(false); }
  }
  return <section className={styles.fields} aria-label='Archive and retention'>
    <h3>{archived ? 'Archived history' : 'Archive post'}</h3>
    <p className={styles.muted}>{post.archive?.message ?? 'Refresh the revision to check archive eligibility. Archived history is retained read-only; recover content by duplicating a new manual draft.'}</p>
    {archived && post.archive?.archived_at && <p role='status'>Archived at {post.archive.archived_at} (UTC). The original remains available in the Archived queue.</p>}
    {mutation.error && <SocialErrorBanner error={mutation.error} onRetry={eligible && !disabled ? archive : undefined} />}
    {!archived && <><button type='button' className={styles.button} disabled={disabled || mutation.isPending || !eligible} aria-expanded={confirming} onClick={() => setConfirming(!confirming)}>Archive post</button>
      {disabled && <p className={styles.muted}>Save or discard local edits and refresh a changed revision before archiving.</p>}
      {confirming && <div className={styles.schedule}><p>Keep this original as read-only history? Revisions, sources, approvals and delivery evidence are retained. Recovery creates a new manual draft. Archive never cancels delivery or deletes remote posts.</p><button type='button' className={styles.button} disabled={disabled || mutation.isPending || !eligible} onClick={archive}>Confirm archive</button><button type='button' className={styles.button} disabled={mutation.isPending} onClick={() => setConfirming(false)}>Keep post open</button></div>}
    </>}
  </section>;
}
