'use client';

import { decodeControls, SocialAccount, SocialPost, SocialSummary, SocialSystemStatus } from '@/lib/api/social';
import { useSocialAccounts, useSocialMutation, useSocialPost, useSocialPosts, useSocialSystem } from '@/lib/hooks/useSocial';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import SocialComposer from './SocialComposer';
import { SocialErrorBanner } from './SocialNotice';
import { httpsUrl, platformLabels } from './socialDocument';
import styles from './social.module.css';

type View = 'drafts' | 'pending' | 'scheduled' | 'history' | 'needs_attention';
const viewLabels: Record<View, string> = { drafts: 'Drafts', pending: 'Pending review', scheduled: 'Scheduled', history: 'History', needs_attention: 'Needs attention' };
export function SocialSystemStrip({ status, error, refresh }: { status?: SocialSystemStatus; error?: unknown; refresh: () => void }) {
  const [editingControls, setEditingControls] = useState(false);
  const [reason, setReason] = useState('');
  const controls = useSocialMutation();
  const [now, setNow] = useState(() => Date.now());
  const heartbeat = status?.worker.heartbeat_at;
  const scan = status?.worker.last_scan_at;
  const health = status?.worker.state;
  const freshnessLimit = health === 'active' ? 45_000 : 150_000;
  useEffect(() => {
    const update = () => setNow(Date.now());
    update();
    const timestamps = [heartbeat, scan].filter((value): value is string => !!value).map(Date.parse);
    const expiry = Math.min(...timestamps) + freshnessLimit + 1 - Date.now();
    const timer = Number.isFinite(expiry) && expiry > 0 ? window.setTimeout(update, expiry) : undefined;
    document.addEventListener('visibilitychange', update);
    return () => { if (timer !== undefined) window.clearTimeout(timer); document.removeEventListener('visibilitychange', update); };
  }, [heartbeat, scan, freshnessLimit]);
  const age = heartbeat ? now - Date.parse(heartbeat) : NaN;
  const scanAge = scan ? now - Date.parse(scan) : NaN;
  const withinLimit = (value: number) => Number.isFinite(value) && value >= -5_000 && value <= freshnessLimit;
  const fresh = ['active', 'idle', 'stopped'].includes(health ?? '') && withinLimit(age) && (health === 'stopped' && scan === null || withinLimit(scanAge));
  async function changeControls() {
    if (!status) return;
    try {
      await controls.run('/controls', { expected_version: status.controls_version, publishing_enabled: !status.publishing_enabled, reason }, decodeControls, { method: 'patch' });
      setEditingControls(false); setReason('');
    } catch { /* Preserve the typed error and exact idempotent command. */ }
  }
  return <div className={styles.fields}>
    <div className={styles.status} aria-label='Publishing system status'><strong>{status ? status.publishing_enabled ? 'Publishing enabled' : 'Publishing paused' : 'Publishing status unavailable'}</strong><span>{fresh && health ? `Worker: ${health}` : heartbeat ? 'Worker heartbeat stale or unavailable' : 'Worker health unavailable'}</span><button className={styles.button} type='button' onClick={refresh}>Refresh status</button><button type='button' className={styles.button} disabled={!status || controls.isPending} aria-expanded={editingControls} onClick={() => setEditingControls(!editingControls)}>{status?.publishing_enabled ? 'Pause publishing' : 'Publishing controls'}</button></div>
    {editingControls && status && <div className={styles.schedule}><p>{status.publishing_enabled ? 'Pausing stops new dispatches. Already accepted or in-flight requests may complete.' : 'Enabling permits approved deliveries when backend account and adapter gates pass. Automatic generation and approval remain off.'}</p><label>Reason for control change<input value={reason} disabled={controls.isPending} onChange={e => setReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={controls.isPending || !reason.trim()} onClick={changeControls}>{status.publishing_enabled ? 'Confirm pause' : 'Enable publishing'}</button></div>}
    {controls.error && <SocialErrorBanner error={controls.error} context='controls' />}
    {status && <p className={styles.muted}>Available adapters: {status.adapters_available.join(', ') || 'none'}. {Object.keys(status.queue_counts).length ? Object.entries(status.queue_counts).map(([state, count]) => `${state.replaceAll('_', ' ')}: ${count}`).join(' · ') : 'No queued destinations reported.'} Automatic publishing is off.</p>}
    {!!error && <SocialErrorBanner error={error} onRetry={refresh} />}
  </div>;
}
function DeliverySummary({ post, accounts }: { post: SocialSummary; accounts: SocialAccount[] }) {
  return <>{post.publication && <><span className={styles.muted}>{post.publication.requested_local_time ?? 'Local time unavailable'} · {post.publication.schedule_timezone ?? 'Timezone unavailable'}</span>{post.publication.scheduled_for && <span className={styles.muted}>Due: {post.publication.scheduled_for} (UTC)</span>}<span className={styles.muted}>Created by {post.created_by ?? "Identity unavailable"} · approved by {post.publication.approved_by}</span></>}{post.targets.map(t => <span key={t.id} className={styles.muted}>{platformLabels[t.platform]} · {accounts.find(a => a.id === t.account_id)?.display_name ?? t.account_id}: {t.state.replaceAll('_', ' ')}{t.published_at ? ` · confirmed ${t.published_at} (UTC)` : ''} </span>)}</>;
}
function HistoryLinks({ post }: { post: SocialSummary }) {
  return <>{post.targets.map(t => {
    const url = t.state === 'published' ? httpsUrl(t.remote_url) : undefined;
    return url ? <a key={t.id} href={url} target='_blank' rel='noopener noreferrer'>View {platformLabels[t.platform]} published post</a> : null;
  })}</>;
}
export default function SocialWorkspace() {
  const router = useRouter();
  const [view, setView] = useState<View>('pending');
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string>();
  const [unsaved, setUnsaved] = useState(false);
  const list = useSocialPosts(page, view === 'drafts' ? 'draft' : view === 'pending' ? 'pending_review' : undefined, true, view === 'scheduled' || view === 'history' || view === 'needs_attention' ? view : 'all');
  const detail = useSocialPost(selected);
  const accounts = useSocialAccounts();
  const system = useSocialSystem();
  const posts = list.data?.posts;
  function mayLeave() { return !unsaved || window.confirm('This draft has unsaved edits. Leave without saving?'); }
  function changeView(next: View) { if (next !== view && mayLeave()) { setView(next); setPage(1); setSelected(undefined); setUnsaved(false); } }
  return <div className={styles.workspace}>
    <div className={styles.toolbar}><p><strong>Manual approval</strong> is the default. Review the evidence and every selected account.</p><Link href='/admin/social/new' className={`${styles.button} ${styles.primary}`}>Create manual post</Link></div>
    <SocialSystemStrip status={system.data} error={system.error} refresh={() => system.refetch()} />
    <nav className={styles.tabs} aria-label='Social sections'>{(Object.keys(viewLabels) as View[]).map(key => <button type='button' key={key} aria-pressed={view === key} onClick={() => changeView(key)}>{viewLabels[key]}</button>)}<Link href='/admin/social/accounts' className={styles.button}>Accounts</Link></nav>
    {accounts.error && <SocialErrorBanner error={accounts.error} onRetry={() => accounts.refetch()} />}
      <div className={styles.toolbar}><div><h2>{viewLabels[view]}</h2><p className={styles.muted}>{list.data ? `${list.data.total} ${view === 'drafts' ? 'drafts' : view === 'pending' ? 'posts awaiting review' : view === 'needs_attention' ? 'posts needing attention' : `${view} posts`}` : 'Loading compact post summaries…'}</p>{(view === 'scheduled' || view === 'history' || view === 'needs_attention') && <p className={styles.muted}>Global delivery results. Mixed posts can appear in several views; each account keeps its independent result.</p>}</div><button className={styles.button} type='button' disabled={list.isFetching} onClick={() => list.refetch()}>Refresh list</button></div>
      {list.error && <SocialErrorBanner error={list.error} onRetry={() => list.refetch()} />}
      {list.isPending && <p role='status'>Loading posts…</p>}
      <div className={styles.reviewGrid}><aside className={styles.queue} aria-label='Post queue'>
        {posts?.length === 0 && <div className={styles.empty}><p>No matching posts.</p><p>Create a manual draft or choose another view.</p></div>}
        {posts?.map(p => <div key={p.id} className={styles.fields}><button className={styles.draft} type='button' aria-pressed={selected === p.id} onClick={() => { if (p.id !== selected && mayLeave()) { setSelected(p.id); setUnsaved(false); } }}><span className={styles.tag}>{p.origin_type} · {p.content_type}</span><strong>{p.title}</strong><span className={styles.muted}>{p.editorial_state.replaceAll('_', ' ')} · {p.delivery_status.replaceAll('_', ' ')}</span><DeliverySummary post={p} accounts={accounts.data ?? []} /></button>{view === 'history' && <HistoryLinks post={p} />}</div>)}
        {list.data && <div className={styles.pagination}><button type='button' className={styles.button} disabled={page === 1 || list.isFetching} onClick={() => { if (mayLeave()) { setPage(page - 1); setSelected(undefined); setUnsaved(false); } }}>Previous page</button><span className={styles.muted}>Page {list.data.page}</span><button type='button' className={styles.button} disabled={!list.data.has_more || list.isFetching} onClick={() => { if (mayLeave()) { setPage(page + 1); setSelected(undefined); setUnsaved(false); } }}>Next page</button></div>}
      </aside><div className={styles.fields}>
        {detail.error && <SocialErrorBanner error={detail.error} onRetry={() => detail.refetch()} />}
        {selected && detail.isPending && <p className={styles.empty} role='status'>Loading the selected revision…</p>}
        {selected && detail.data && <><Link href={`/admin/social/${selected}`}>Open this post in the full composer</Link><SocialComposer key={selected} initialPost={detail.data} accounts={accounts.data ?? []} accountsAvailable={!!accounts.data && !accounts.error} system={system.data} onSaved={p => router.push(`/admin/social/${p.id}`)} onDirtyChange={setUnsaved} /></>}
        {!selected && <div className={styles.empty}><h3>Queue and preview</h3><p>Select a post to review its sources, account versions, schedule, and delivery results.</p></div>}
      </div></div>
  </div>;
}

export function SocialEditorPage({ postId }: { postId?: string }) {
  const router = useRouter();
  const post = useSocialPost(postId);
  const accounts = useSocialAccounts();
  const system = useSocialSystem();
  function saved(p: SocialPost) { router.push(`/admin/social/${p.id}`); }
  return <div className={styles.workspace}>
    <SocialSystemStrip status={system.data} error={system.error} refresh={() => system.refetch()} />
    {accounts.error && <SocialErrorBanner error={accounts.error} onRetry={() => accounts.refetch()} />}
    {postId && post.error && <SocialErrorBanner error={post.error} onRetry={() => post.refetch()} />}
    {postId && post.isPending && <p role='status' className={styles.empty}>Loading draft…</p>}
    {(!postId || post.data) && <SocialComposer key={postId ?? 'new'} initialPost={post.data} accounts={accounts.data ?? []} accountsAvailable={!!accounts.data && !accounts.error} system={system.data} onSaved={saved} />}
  </div>;
}
