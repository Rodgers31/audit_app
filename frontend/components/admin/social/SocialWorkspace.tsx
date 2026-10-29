'use client';

import { decodeControls, SocialAccount, SocialPost, SocialSummary, SocialSystemStatus } from '@/lib/api/social';
import { useSocialAccounts, useSocialMutation, useSocialPost, useSocialPosts, useSocialSystem } from '@/lib/hooks/useSocial';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import SocialComposer from './SocialComposer';
import SocialPreview from './SocialPreview';
import { useAuth } from '@/lib/auth/AuthProvider';
import { SocialErrorBanner } from './SocialNotice';
import { httpsUrl, platformLabels } from './socialDocument';
import styles from './social.module.css';
import { queueDefaults, queueQuery, readQueueSelection, type QueueSelection, type QueueView } from './socialQueue';

type View = QueueView;
const viewLabels: Record<View, string> = { pending: 'Ready for review', drafts: 'Drafts in progress', needs_attention: 'Needs attention', scheduled: 'Scheduled', history: 'Delivery history', archived: 'Archived' };
const contentLabels: Record<string, string> = { debt_update: 'Financial update', budget_update: 'Budget update', new_report: 'New report', dataset_availability: 'Report availability', audit_finding: 'Audit finding', correction: 'Correction' };
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
    <div className={styles.status} aria-label='Publishing system status'><strong>{status ? status.publishing_enabled ? 'Publishing enabled' : 'Publishing paused' : 'Publishing status unavailable'}</strong><span className={styles.muted}>{status?.publishing_enabled === false ? 'You can edit and review drafts. New deliveries are paused; requests already in flight may complete.' : 'Every delivery requires its own approval and account checks.'}</span><details className={styles.systemDetails}><summary>System details</summary><div><span>{fresh && health ? `Worker: ${health}` : heartbeat ? 'Worker heartbeat stale or unavailable' : 'Worker health unavailable'}</span><button className={styles.button} type='button' onClick={refresh}>Refresh status</button><button type='button' className={styles.button} disabled={!status || controls.isPending} aria-expanded={editingControls} onClick={() => setEditingControls(!editingControls)}>{status?.publishing_enabled ? 'Pause publishing' : 'Publishing controls'}</button></div></details></div>
    {editingControls && status && <div className={styles.schedule}><p>{status.publishing_enabled ? 'Pausing stops new dispatches. Already accepted or in-flight requests may complete.' : 'Enabling permits approved deliveries when backend account and adapter gates pass. Automatic generation and approval remain off.'}</p><label>Reason for control change<input value={reason} disabled={controls.isPending} onChange={e => setReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={controls.isPending || !reason.trim()} onClick={changeControls}>{status.publishing_enabled ? 'Confirm pause' : 'Enable publishing'}</button></div>}
    {controls.error && <SocialErrorBanner error={controls.error} context='controls' />}
    {editingControls && status && <p className={styles.muted}>Available adapters: {status.adapters_available.join(', ') || 'none'}. {Object.keys(status.queue_counts).length ? Object.entries(status.queue_counts).map(([state, count]) => `${state.replaceAll('_', ' ')}: ${count}`).join(' · ') : 'No queued destinations reported.'} Automatic publishing is off.</p>}
    {!!error && <SocialErrorBanner error={error} onRetry={refresh} />}
  </div>;
}
function DeliverySummary({ post, accounts, historical, attention }: { post: SocialSummary; accounts: SocialAccount[]; historical: boolean; attention: boolean }) {
  if (attention) {
    const attentionStates = new Set(['failed', 'blocked', 'reconciling', 'outcome_unknown']);
    const currentIds = new Set(post.targets.map(t => t.id));
    const current = post.targets.filter(t => attentionStates.has(t.state));
    const past = post.historical_targets.filter(t => attentionStates.has(t.state) && !currentIds.has(t.id));
    return <>{current.map(t => <span key={t.id} className={styles.muted}>Current {platformLabels[t.platform]} · {accounts.find(a => a.id === t.account_id)?.display_name ?? t.account_id}: {t.state.replaceAll('_', ' ')}</span>)}{past.map(t => <span key={t.id} className={styles.muted}>Historical {platformLabels[t.platform]} · {accounts.find(a => a.id === t.account_id)?.display_name ?? t.account_id}: {t.state.replaceAll('_', ' ')}</span>)}{post.historical_target_count > 20 && <span className={styles.muted}>Some older deliveries are on later history pages. Select this post to inspect all delivery history.</span>}</>;
  }
  if (historical) return <>{post.historical_targets.map(t => <span key={t.id} className={styles.muted}>Historical {platformLabels[t.platform]} · {accounts.find(a => a.id === t.account_id)?.display_name ?? t.account_id}: {t.state.replaceAll('_', ' ')}{t.published_at ? ` · confirmed ${t.published_at} (UTC)` : ''}{t.scheduled_for ? ` · due ${t.scheduled_for} (UTC)` : ''}</span>)}{post.historical_target_count > 20 && <span className={styles.muted}>Showing 20 of {post.historical_target_count} historical deliveries. Select to inspect all.</span>}</>;
  return <>{post.publication && <><span className={styles.muted}>{post.publication.requested_local_time ?? 'Local time unavailable'} · {post.publication.schedule_timezone ?? 'Timezone unavailable'}</span>{post.publication.scheduled_for && <span className={styles.muted}>Due: {post.publication.scheduled_for} (UTC)</span>}<span className={styles.muted}>Created by {post.created_by ?? "Identity unavailable"} · authorized by {post.publication.approved_by ?? 'approved policy'}</span></>}{post.targets.map(t => <span key={t.id} className={styles.muted}>{platformLabels[t.platform]} · {accounts.find(a => a.id === t.account_id)?.display_name ?? t.account_id}: {t.state.replaceAll('_', ' ')}{t.published_at ? ` · confirmed ${t.published_at} (UTC)` : ''} </span>)}</>;
}
function HistoryLinks({ post }: { post: SocialSummary }) {
  return <>{post.historical_targets.map(t => {
    const url = t.state === 'published' ? httpsUrl(t.remote_url) : undefined;
    return url ? <a key={t.id} href={url} target='_blank' rel='noopener noreferrer'>View {platformLabels[t.platform]} published post</a> : null;
  })}</>;
}
export function QueuePostPreview({ summary, accounts, refreshQueue }: { summary: SocialSummary; accounts: SocialAccount[]; refreshQueue: () => void }) {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState('');
  const post = useSocialPost(summary.id, open);
  const saved = post.data?.revision_id === summary.revision_id ? post.data : undefined;
  const target = saved?.document.targets.find(t => t.account_id === selected) ?? saved?.document.targets[0];
  return <div className={styles.queuePreview}>
    <button type='button' className={styles.button} aria-label={`${open ? 'Hide preview' : 'Preview post'}: ${summary.title}`} aria-expanded={open} aria-controls={`preview-${summary.id}`} onClick={() => setOpen(!open)}>{open ? 'Hide preview' : 'Preview post'}</button>
    {open && <div id={`preview-${summary.id}`} className={styles.fields}>
      <h4>Post preview</h4>
      {post.isFetching && <p role='status'>Loading saved post…</p>}
      {post.error && <SocialErrorBanner error={post.error} onRetry={() => post.refetch()} />}
      {!post.isFetching && !post.error && !saved && <p role='status'>The saved revision changed. <button type='button' onClick={() => { post.refetch(); refreshQueue(); }}>Refresh drafts</button></p>}
      {saved && <>
        <p className={styles.muted}>Saved revision · Open the draft to edit or check its evidence.</p>
        {saved.document.targets.length > 1 && <label>Preview account<select value={target?.account_id ?? ''} onChange={event => setSelected(event.target.value)}>{saved.document.targets.map(t => <option key={t.account_id} value={t.account_id}>{accounts.find(a => a.id === t.account_id)?.display_name ?? 'Account unavailable'}</option>)}</select></label>}
        <SocialPreview master={saved.document.master} target={target} account={accounts.find(a => a.id === target?.account_id)} />
      </>}
    </div>}
  </div>;
}
export default function SocialWorkspace() {
  const { user } = useAuth();
  const [selection, setSelection] = useState<QueueSelection>(queueDefaults);
  const [queueReady, setQueueReady] = useState(false);
  const {view, origin, category, page} = selection;
  useEffect(() => {
    const restore = () => { setSelection(readQueueSelection(window.location.search)); setQueueReady(true); };
    restore(); window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, []);
  function selectQueue(next: QueueSelection) {
    setSelection(next); const query = queueQuery(next);
    window.history.replaceState(window.history.state, '', '/admin/social' + (query ? '?' + query : ''));
  }
  const query = queueQuery(selection);
  const draftHref = (id: string) => `/admin/social/${id}${query ? '?queue=' + encodeURIComponent(query) : ''}`;
  const list = useSocialPosts(page, view === 'archived' ? 'archived' : view === 'drafts' ? 'draft' : view === 'pending' ? 'pending_review' : undefined, queueReady, view === 'scheduled' || view === 'history' || view === 'needs_attention' ? view : 'all', origin || undefined, category || undefined);
  const accounts = useSocialAccounts();
  const system = useSocialSystem();
  const posts = list.data?.posts;
  function changeView(next: View) { selectQueue({...selection, view:next, page:1}); }
  return <div className={styles.workspace}>
    <SocialSystemStrip status={system.data} error={system.error} refresh={() => system.refetch()} />
    <div className={styles.queueHeading}>
      <div><h2>{viewLabels[view]}</h2><p className={styles.muted}>{list.data ? `${list.data.total} ${view === 'scheduled' ? 'scheduled ' : view === 'history' ? 'history ' : ''}${list.data.total === 1 ? 'post' : 'posts'}${view === 'needs_attention' ? ' needing attention' : view === 'pending' ? ' awaiting review' : ''}` : 'Loading saved drafts…'}</p><p className={styles.muted}>Preview the post here, or open the draft to edit and check its evidence.</p></div>
      <Link href='/admin/social/new' className={styles.button}>Write a post</Link>
    </div>
    <div className={styles.queueControls}>
      <nav className={styles.tabs} aria-label='Review queues'>{(['pending', 'drafts', 'needs_attention'] as View[]).map(key => <button type='button' key={key} aria-pressed={view === key} onClick={() => changeView(key)}>{viewLabels[key]}</button>)}</nav>
      <details className={styles.filters} open={view !== 'pending' && view !== 'drafts' && view !== 'needs_attention' || !!origin || !!category}><summary>Filter & history</summary><div className={styles.actions}>
        <label>View<select value={view} onChange={e => changeView(e.target.value as View)}>{(Object.keys(viewLabels) as View[]).map(key => <option value={key} key={key}>{viewLabels[key]}</option>)}</select></label>
        <label>Origin<select value={origin} onChange={e => {selectQueue({...selection,origin:e.target.value,page:1});}}><option value=''>Generated & manual</option><option value='manual'>Written manually</option><option value='generated'>Generated from data</option></select></label>
        <label>Content type<select value={category} onChange={e => {selectQueue({...selection,category:e.target.value,page:1});}}><option value=''>All topics</option>{Object.entries(contentLabels).map(([key,label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      </div></details>
      <button className={styles.button} type='button' disabled={list.isFetching} onClick={() => list.refetch()}>Refresh list</button>
    </div>
    {accounts.error && <SocialErrorBanner error={accounts.error} onRetry={() => accounts.refetch()} />}
    {list.error && <SocialErrorBanner error={list.error} onRetry={() => list.refetch()} />}
    {list.isPending && <div className={styles.empty} role='status'>Loading posts and review states…</div>}
    {posts?.length === 0 && <div className={styles.empty}><h3>{view === 'pending' ? 'No drafts awaiting review' : 'No matching posts'}</h3><p>{view === 'pending' ? 'New eligible changes appear here after draft generation succeeds. A successful data refresh alone does not mean a draft was created.' : 'Choose another queue or clear the filters to see more posts.'}</p><Link href='/admin/ingestion'>Check data updates & draft outcomes</Link><Link href='/admin/social/automation'>Inspect draft automation</Link></div>}
    <section className={styles.draftList} aria-label='Post queue'>
      {posts?.map(p => <article key={p.id} className={styles.queueCard}>
        <div className={styles.fields}><div className={styles.actions}><span className={styles.badge}>{p.origin_type === 'generated' ? 'Generated from data' : 'Written manually'}</span><span className={styles.muted}>{contentLabels[p.content_type] ?? p.content_type.replaceAll('_', ' ')}</span></div>
          <h3><Link href={draftHref(p.id)}>{p.title}</Link></h3>
          <p className={styles.muted}>{p.editorial_state === 'pending_review' ? 'Human review required' : p.editorial_state.replaceAll('_',' ')}{p.delivery_status !== 'not_requested' && p.delivery_status !== 'draft' ? ` · ${p.delivery_status.replaceAll('_',' ')}` : ''}</p>
          {(view === 'history' || view === 'needs_attention' || view === 'scheduled') && <DeliverySummary post={p} accounts={accounts.data ?? []} historical={view === 'history'} attention={view === 'needs_attention'} />}
          {view === 'history' && <HistoryLinks post={p} />}
        </div>
        <Link href={draftHref(p.id)} className={`${styles.button} ${styles.primary}`} aria-label={`${view === 'history' ? 'View results' : 'Open draft'}: ${p.title}`}>{view === 'history' ? 'View results' : 'Open draft'} <span aria-hidden='true'>→</span></Link>
        <QueuePostPreview key={`${user?.id}:${p.id}:${p.revision_id}`} summary={p} accounts={accounts.data ?? []} refreshQueue={() => list.refetch()} />
      </article>)}
    </section>
    {list.data && list.data.total > 0 && <div className={styles.pagination}><button type='button' className={styles.button} disabled={page === 1 || list.isFetching} onClick={() => selectQueue({...selection,page:page-1})}>Previous page</button><span className={styles.muted}>Page {list.data.page}</span><button type='button' className={styles.button} disabled={!list.data.has_more || list.isFetching} onClick={() => selectQueue({...selection,page:page+1})}>Next page</button></div>}
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
