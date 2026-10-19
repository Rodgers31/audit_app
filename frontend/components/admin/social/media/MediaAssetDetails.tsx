'use client';
import Link from 'next/link';
import { useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { decodeMediaAsset, socialMediaApi } from '@/lib/api/socialMedia';
import { SocialApiError } from '@/lib/api/social';
import { mediaKeys, useMediaAccess } from '@/lib/hooks/useSocialMedia';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import styles from './media.module.css';

export default function MediaAssetDetails({ id, selected, onArchived }: { id: string; selected: boolean; onArchived: () => void }) {
  const { actor, enabled } = useMediaAccess(), qc = useQueryClient(), command = useSocialMutation();
  const [page, setPage] = useState(1), [confirm, setConfirm] = useState(false), [reason, setReason] = useState(''), [archived, setArchived] = useState(false);
  const busy = useRef(false);
  const latestVersion = useRef(0);
  const usage = useQuery({ queryKey: [...mediaKeys.root(actor), 'usage', id, page], queryFn: async ({ signal }) => {
    const result = await socialMediaApi.usage(id, page, signal);
    if (result.asset.version < latestVersion.current) throw new SocialApiError('MEDIA_VERSION_REGRESSED', 'Asset usage returned an older version. Refresh before archiving.');
    latestVersion.current = result.asset.version;
    return result;
  }, enabled, retry: false, staleTime: 0, refetchOnWindowFocus: false });
  const data = usage.data, eligible = !!data?.archive_eligible && data.asset.version >= latestVersion.current && !selected && !archived && !usage.isFetching && !usage.error;
  async function archive() {
    if (busy.current || !eligible || !data || !reason.trim()) return;
    busy.current = true;
    const before = data.asset;
    try {
      await command.run(`/media/assets/${encodeURIComponent(id)}/archive`, { expected_version: before.version, reason: reason.trim() }, value => {
        const result = decodeMediaAsset(value);
        if (result.id !== id || result.state !== 'archived' || result.version !== before.version + 1 || JSON.stringify({ ...result, state: before.state, version: before.version }) !== JSON.stringify(before)) throw new SocialApiError('INVALID_MEDIA_RESPONSE', 'The archive receipt did not confirm the unchanged retained asset. Retry the same command.');
        return result;
      });
      setArchived(true); setConfirm(false);
      await qc.invalidateQueries({ queryKey: mediaKeys.root(actor) });
      onArchived();
    } catch { /* The typed mutation error remains visible; its command key is retained. */ }
    finally { busy.current = false; }
  }
  return <section className={styles.panel} aria-label='Media usage and archive'>
    <h3>Asset usage and retention</h3>
    {usage.isPending && <p role='status'>Loading asset usage…</p>}
    {usage.error && <p role='alert' className={styles.error}>{usage.error.message}</p>}
    <button type='button' className={styles.button} disabled={usage.isFetching || command.isPending} onClick={() => { setConfirm(false); void usage.refetch(); }}>Refresh usage</button>
    {data && <>
      <p>Used by {data.total} historical revisions</p>
      <ul>{data.references.map(r => <li key={r.revision_id}><Link href={`/admin/social/${r.post_id}`}>{r.title}</Link> · Revision {r.revision_no} · {r.revision_id}</li>)}</ul>
      <div className={styles.actions}><button type='button' className={styles.button} disabled={page === 1 || usage.isFetching || command.isPending} onClick={() => setPage(page - 1)}>Previous usage page</button><span>Page {page}</span><button type='button' className={styles.button} disabled={!data.has_more || usage.isFetching || command.isPending} onClick={() => setPage(page + 1)}>Next usage page</button></div>
      <p>{data.archive_reason}</p>
      {selected && <p>Remove this asset from the current selection before archiving.</p>}
      {archived ? <p role='status'>Asset archived. Objects, quota and history are retained.</p> : <button type='button' className={styles.button} disabled={!eligible || command.isPending} aria-expanded={confirm} onClick={() => setConfirm(!confirm)}>Archive unused asset</button>}
      {confirm && <div className={styles.panel}><p>Hide this unused asset from the library? Objects, quota and audit history stay retained. This does not delete stored bytes or grant retirement authority.</p><label>Archive reason<input value={reason} maxLength={500} disabled={command.isPending} onChange={e => setReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={!eligible || command.isPending || !reason.trim()} onClick={archive}>Confirm asset archive</button><button type='button' className={styles.button} disabled={command.isPending} onClick={() => setConfirm(false)}>Keep asset</button></div>}
    </>}
    {command.error && <p role='alert' className={styles.error}>{command.error.message}</p>}
  </section>;
}
