'use client';

import { useQuery, useQueryClient } from '@tanstack/react-query';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { socialApi } from '@/lib/api/social';
import { socialMediaApi } from '@/lib/api/socialMedia';
import { Composition, RenderJob, studioApi, templateRoles } from '@/lib/api/socialStudio';
import { SocialErrorBanner } from './SocialNotice';
import { httpsUrl } from './socialDocument';
import styles from './social.module.css';

export default function SocialStudio() {
  const cache = useQueryClient();
  const caps = useQuery({ queryKey: ['studio-capabilities'], queryFn: studioApi.capabilities, retry: false });
  const posts = useQuery({ queryKey: ['studio-source-posts'], queryFn: () => socialApi.posts(1), retry: false });
  const [postId, setPostId] = useState(''), [template, setTemplate] = useState('new_report'), [kind, setKind] = useState<'graphic' | 'video'>('video');
  const post = useQuery({ queryKey: ['studio-source', postId], queryFn: () => socialApi.post(postId), enabled: !!postId, retry: false });
  const [title, setTitle] = useState(''), [factTexts, setFactTexts] = useState<Record<string, string>>({}), [sourceUrl, setSourceUrl] = useState('');
  const [page, setPage] = useState(1), [selected, setSelected] = useState('');
  const jobs = useQuery({ queryKey: ['studio-jobs', page], queryFn: () => studioApi.jobs(page), retry: false });
  const job = jobs.data?.jobs.find(j => j.id === selected);
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [notice, setNotice] = useState('');
  const [preview, setPreview] = useState<{ id: string; sha: string; url: string }>(), [subtitles, setSubtitles] = useState<string>(), [reviewed, setReviewed] = useState(false);
  const activeJob = useRef(selected);
  activeJob.current = selected;
  const [assetId, setAssetId] = useState(''), [attachedPost, setAttachedPost] = useState('');
  const assets = useQuery({ queryKey: ['studio-assets'], queryFn: () => socialMediaApi.library(1, '', ''), enabled: !!job?.approved_sha256, retry: false });
  useEffect(() => { setReviewed(false); setPreview(undefined); setSubtitles(undefined); setAssetId(''); }, [selected]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview.url); }, [preview]);
  useEffect(() => () => { if (subtitles) URL.revokeObjectURL(subtitles); }, [subtitles]);
  useEffect(() => { if (post.data) { setTitle(post.data.title.slice(0, 70)); setSourceUrl(post.data.references[0]?.url ?? ''); } }, [post.data]);
  async function act(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(undefined); setNotice('');
    try { await action(); setNotice(success); await cache.invalidateQueries({ queryKey: ['studio-jobs'] }); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  async function create() {
    if (!post.data) return;
    const roles = templateRoles[template];
    const composition: Composition = { schema_version: 1, template, template_version: 1, kind, revision_id: post.data.revision_id, title, facts: roles.map(id => ({ id, text: factTexts[id] ?? '', source_url: sourceUrl })), scenes: (kind === 'graphic' ? [roles[0]] : roles).map(id => ({ fact_id: id, seconds: kind === 'video' ? Math.ceil(15 / roles.length) : 15 })) };
    await act(async () => { const result = await studioApi.create(composition, crypto.randomUUID()); setSelected(result.id); setPage(1); }, 'Render queued. A separately configured local operator must run it.');
  }
  async function loadPreview(current: RenderJob) {
    await act(async () => {
      const url = await studioApi.media(current);
      if (activeJob.current !== current.id) { URL.revokeObjectURL(url); return; }
      setPreview({ id: current.id, sha: current.sha256!, url });
      setReviewed(false);
    }, 'The preview bytes match the inspected checksum.');
  }
  const roles = templateRoles[template];
  const previewMatches = !!job && preview?.id === job.id && preview.sha === job.sha256;
  const compatibleAssets = assets.data?.assets.filter(a => a.sha256 === job?.approved_sha256) ?? [];
  return <div className={styles.workspace}>
    <nav className={styles.tabs} aria-label='Social sections'><Link href='/admin/social'>Review queue</Link><Link href='/admin/social/accounts'>Accounts</Link></nav>
    <div className={styles.status}><strong>Local editorial studio</strong><span>Rendering and metrics are separate from delivery. Uploads and automatic publishing stay off.</span></div>
    {!!error && <SocialErrorBanner error={error} />}{notice && <p role='status' className={styles.success}>{notice}</p>}
    {caps.error && <SocialErrorBanner error={caps.error} onRetry={() => caps.refetch()} />}
    {caps.data && !caps.data.rendering_available && <p className={styles.notice}>{caps.data.unavailable_reason}</p>}
    <section className={styles.editor} aria-labelledby='studio-create'><div className={styles.editorHeading}><h2 id='studio-create'>Graphics and short video</h2></div><div className={styles.editorBody}>
      <p>Use a current draft with source references. Templates v1 produce 9:16 cards and 15–45 second videos with visible captions and a downloadable transcript. Voiceover is absent.</p>
      {posts.error && <SocialErrorBanner error={posts.error} onRetry={() => posts.refetch()} />}
      <label>Source post<select value={postId} disabled={busy} onChange={e => setPostId(e.target.value)}><option value=''>Choose from the latest 20 posts</option>{posts.data?.posts.map(p => <option key={p.id} value={p.id}>{p.title}</option>)}</select></label>
      {post.error && <SocialErrorBanner error={post.error} onRetry={() => post.refetch()} />}
      <div className={styles.twoFields}><label>Template<select value={template} disabled={busy} onChange={e => { setTemplate(e.target.value); setFactTexts({}); }}>{Object.keys(templateRoles).map(t => <option key={t} value={t}>{t.replaceAll('_', ' ')}</option>)}</select></label><label>Output<select value={kind} disabled={busy} onChange={e => setKind(e.target.value as 'graphic' | 'video')}><option value='video'>Video · 9:16 with captions</option><option value='graphic'>Graphic · 9:16 fact card</option></select></label></div>
      <label>Title · 70 characters<input maxLength={70} value={title} disabled={busy} onChange={e => setTitle(e.target.value)} /></label>
      <label>Evidence reference<select value={sourceUrl} disabled={busy} onChange={e => setSourceUrl(e.target.value)}><option value=''>Choose an existing source</option>{post.data?.references.map(r => <option key={r.url} value={r.url}>{r.label ?? r.url}</option>)}</select></label>
      {roles.map(role => <label key={role}>Verified {role.replaceAll('_', ' ')} · 180 characters<textarea rows={2} maxLength={180} value={factTexts[role] ?? ''} disabled={busy} onChange={e => setFactTexts(current => ({ ...current, [role]: e.target.value }))} /></label>)}
      <p className={styles.muted}>Version 1 supports printable English text. Check every number, unit, entity and period against the cited source. Unresolved placeholders are rejected.</p>
      <button type='button' className={`${styles.button} ${styles.primary}`} disabled={busy || !caps.data?.rendering_available || !post.data || !sourceUrl || !title.trim() || roles.some(r => !factTexts[r]?.trim())} onClick={create}>Queue local render</button>
    </div></section>
    <section aria-labelledby='studio-jobs' className={styles.fields}><div className={styles.toolbar}><h2 id='studio-jobs'>Render jobs</h2><button type='button' className={styles.button} disabled={busy || jobs.isFetching} onClick={() => jobs.refetch()}>Refresh render jobs</button></div>
      {jobs.error && <SocialErrorBanner error={jobs.error} onRetry={() => jobs.refetch()} />}
      {jobs.isPending && <p role='status'>Loading render jobs…</p>}{jobs.data?.jobs.length === 0 && <p className={styles.empty}>No local render jobs.</p>}
      <div className={styles.reviewGrid}><aside className={styles.queue} aria-label='Render queue'>{jobs.data?.jobs.map(j => <button type='button' className={styles.draft} aria-pressed={selected === j.id} key={j.id} disabled={busy} onClick={() => setSelected(j.id)}><strong>{j.composition.title}</strong><span>{j.composition.kind} · {j.state}{j.cancel_requested ? ' · cancellation requested' : ''}</span><span>{j.approved_sha256 ? 'Exact derivative approved' : 'Needs review after rendering'}</span></button>)}<div className={styles.pagination}><button type='button' className={styles.button} disabled={busy || page === 1} onClick={() => { setPage(p => p - 1); setSelected(''); }}>Previous jobs</button><span>Page {page}</span><button type='button' className={styles.button} disabled={busy || !jobs.data?.has_more} onClick={() => { setPage(p => p + 1); setSelected(''); }}>Next jobs</button></div></aside>
      {job ? <div className={styles.fields}><h3>{job.composition.title}</h3><p className={styles.muted}>Source revision: {job.revision_id}</p>{job.safe_error && <p role='status' className={styles.notice}>{job.safe_error}</p>}
        {job.composition.scenes.map((s, i) => { const f = job.composition.facts.find(f => f.id === s.fact_id)!; return <div key={i} className={styles.evidence}><strong>Fact {f.id} · {s.seconds}s</strong><p>{f.text}</p>{httpsUrl(f.source_url) && <a href={f.source_url} target='_blank' rel='noopener noreferrer'>Open cited source</a>}</div>; })}
        {(job.state === 'queued' || job.state === 'running') && <button type='button' className={styles.button} disabled={busy || job.cancel_requested} onClick={() => act(() => studioApi.cancel(job, crypto.randomUUID()), 'Cancellation requested. Running tools must stop before the job is terminal.')}>Cancel render</button>}
        {(job.state === 'failed' || job.state === 'cancelled') && job.attempt === 1 && <button type='button' className={styles.button} disabled={busy} onClick={() => act(async () => { const retry = await studioApi.retry(job, crypto.randomUUID()); setSelected(retry.id); setPage(1); }, 'One new render attempt queued. Previous evidence is retained; any result needs fresh checksum review.')}>Retry local render once</button>}
        {job.state === 'ready' && <><p className={styles.mediaId}>SHA-256: {job.sha256}</p><button type='button' className={styles.button} disabled={busy} onClick={() => loadPreview(job)}>Load verified preview</button>
          {previewMatches && <>{job.composition.kind === 'video' ? <video controls preload='metadata' src={preview.url} style={{ width: '100%', maxWidth: 360 }} aria-label='Rendered video with visible burned-in captions' /> : <img src={preview.url} alt={job.composition.facts.map(f => f.text).join(' ')} style={{ width: '100%', maxWidth: 360 }} />}<a href={preview.url} download={`${job.id}.${job.composition.kind === 'video' ? 'mp4' : 'png'}`}>Download exact inspected derivative</a></>}
          <button type='button' className={styles.button} disabled={busy} onClick={() => act(async () => { const url = await studioApi.subtitles(job); if (activeJob.current === job.id) setSubtitles(url); else URL.revokeObjectURL(url); }, 'Timed captions are available.')}>Prepare caption download</button>{subtitles && <a href={subtitles} download={`${job.id}.srt`}>Download timed captions (SRT)</a>}
          {!job.approved_sha256 && <><label className={styles.reviewCheck}><input type='checkbox' checked={reviewed} disabled={busy || !previewMatches} onChange={e => setReviewed(e.target.checked)} />I reviewed these exact bytes, the fact IDs, all facts and source references.</label><button type='button' className={`${styles.button} ${styles.primary}`} disabled={busy || !previewMatches || !reviewed} onClick={() => act(() => studioApi.approve(job, crypto.randomUUID()), 'Exact derivative approved. Adding it to a post still requires a new draft and normal publication review.')}>Approve this checksum</button></>}
          {job.approved_sha256 && <div className={styles.schedule}><p>To use this derivative, its exact bytes must first pass the existing media intake. Uploads are currently off. Select an already inspected matching asset when available.</p>{assets.error && <SocialErrorBanner error={assets.error} onRetry={() => assets.refetch()} />}<label>Matching inspected asset<select value={assetId} onChange={e => setAssetId(e.target.value)} disabled={busy}><option value=''>Choose a matching asset</option>{compatibleAssets.map(a => <option key={a.id} value={a.id}>{a.filename}</option>)}</select></label><button type='button' className={styles.button} disabled={busy || !assetId || !post.data || post.data.revision_id !== job.revision_id} onClick={() => act(async () => { const result = await studioApi.attach(job, assetId, post.data!.version, crypto.randomUUID()); setAttachedPost(result.id); await cache.invalidateQueries({ queryKey: ['studio-source'] }); }, 'Derivative added to a new draft revision. Normal fact review and publishing approval are required.')}>Add approved derivative to source draft</button>{attachedPost && <Link href={`/admin/social/${attachedPost}`}>Review updated draft</Link>}</div>}
        </>}
      </div> : <p className={styles.empty}>Select a job to inspect its facts, captions and exact rendered checksum.</p>}</div>
    </section>
    <StudioCalendar />
    <StudioAnalytics reason={caps.data?.analytics_reason} />
  </div>;
}

function StudioCalendar() {
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7)), [page, setPage] = useState(1);
  const validMonth = /^\d{4}-(0[1-9]|1[0-2])$/.test(month);
  const start = validMonth ? `${month}-01T00:00:00Z` : '';
  const parsed = start ? new Date(start) : null;
  const end = parsed ? new Date(Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth() + 1, 1)).toISOString() : '';
  const result = useQuery({ queryKey: ['studio-calendar', month, page], queryFn: () => studioApi.calendar(start, end, page), enabled: validMonth, retry: false });
  return <section className={styles.fields} aria-labelledby='studio-calendar'><h2 id='studio-calendar'>Publication calendar</h2><label>Month · UTC calendar window<input type='month' value={month} onChange={e => { setMonth(e.target.value); setPage(1); }} /></label><p className={styles.muted}>Each row preserves the approved schedule timezone. Cancelled and revoked history remains visible.</p>{result.error && <SocialErrorBanner error={result.error} onRetry={() => result.refetch()} />}{result.isFetching && <p role='status'>Loading calendar…</p>}{result.data?.items.length === 0 && <p>No scheduled publications in this month.</p>}<ul className={styles.mediaList}>{result.data?.items.map(item => <li className={styles.mediaItem} key={item.publication_id}><Link href={`/admin/social/${item.post_id}`}>{item.title}</Link><p><time dateTime={item.scheduled_for}>{item.scheduled_for}</time> (UTC) · approved timezone {item.timezone ?? 'unavailable'}{item.revoked ? ' · revoked' : ''}{item.cancel_requested ? ' · cancellation requested' : ''}</p></li>)}</ul><div className={styles.pagination}><button type='button' className={styles.button} disabled={page === 1 || result.isFetching} onClick={() => setPage(p => p - 1)}>Previous calendar page</button><span>Page {page}</span><button type='button' className={styles.button} disabled={!result.data?.has_more || result.isFetching} onClick={() => setPage(p => p + 1)}>Next calendar page</button><button type='button' className={styles.button} disabled={!validMonth || result.isFetching} onClick={() => result.refetch()}>Refresh calendar</button></div></section>;
}

function StudioAnalytics({ reason }: { reason?: string }) {
  const [input, setInput] = useState(''), [targetId, setTargetId] = useState(''), [page, setPage] = useState(1);
  const result = useQuery({ queryKey: ['studio-analytics', targetId, page], queryFn: () => studioApi.analytics(targetId, page), enabled: !!targetId, retry: false });
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const update = () => setNow(Date.now());
    const expiries = result.data?.collections.flatMap(c => c.metrics.map(m => Date.parse(m.available_until))).filter(expiry => expiry > Date.now()) ?? [];
    const timer = expiries.length ? window.setTimeout(update, Math.max(1, Math.min(...expiries) - Date.now() + 1)) : undefined;
    document.addEventListener('visibilitychange', update);
    return () => { if (timer !== undefined) window.clearTimeout(timer); document.removeEventListener('visibilitychange', update); };
  }, [result.data, now]);
  return <section className={styles.fields} aria-labelledby='studio-analytics'><h2 id='studio-analytics'>Provider analytics</h2><p>{reason ?? 'Collection availability is being checked.'} Missing observations are unavailable; they never imply zero.</p><form className={styles.fields} onSubmit={e => { e.preventDefault(); setTargetId(input); setPage(1); }}><label>Published target ID<input value={input} onChange={e => setInput(e.target.value)} required pattern='[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}' /></label><button type='submit' className={styles.button}>View stored provider observations</button></form>{result.error && <SocialErrorBanner error={result.error} onRetry={() => result.refetch()} />}{targetId && result.isFetching && <p role='status'>Loading provider observations…</p>}{result.data?.reason && <p role='status'>{result.data.reason}</p>}{result.data?.collections.map(c => <article key={c.id} className={styles.schedule}><h3>{result.data.platform} · {c.state}</h3><p>Remote post {c.remote_id} · collected {c.created_at}</p>{c.reason && <p>{c.reason}</p>}{c.metrics.map((m, i) => <div key={i} className={styles.evidence}><strong>{m.name}: {m.status === 'unavailable' ? `Unavailable (${m.reason})` : `${m.value} ${m.unit}`} · {Date.parse(m.available_until) <= now ? 'stale' : m.freshness}</strong><p>{m.period} · {m.window_start} to {m.window_end}</p><p>Provider API {m.api_version} · observed {m.collected_at} · fresh until {m.available_until}</p></div>)}</article>)}{result.data && <div className={styles.pagination}><button type='button' className={styles.button} disabled={page === 1 || result.isFetching} onClick={() => setPage(p => p - 1)}>Previous observations</button><span>Page {page}</span><button type='button' className={styles.button} disabled={!result.data.has_more || result.isFetching} onClick={() => setPage(p => p + 1)}>Next observations</button><button type='button' className={styles.button} disabled={result.isFetching} onClick={() => result.refetch()}>Refresh observations</button></div>}</section>;
}
