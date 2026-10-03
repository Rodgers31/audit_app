'use client';

import { decodePost, decodePublication, DocumentTarget, PublishInput, SocialAccount, SocialApiError, SocialDraftInput, SocialPost, SocialSystemStatus, SocialValidation, socialApi, toSocialError } from '@/lib/api/social';
import { useSocialDeliveryStatus, useSocialMutation, useSocialPost } from '@/lib/hooks/useSocial';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { draftFingerprint, emptyDocument, httpsUrl, platformLabels, resolveCivilTime, resolveContent, supportedFormats, targetHints } from './socialDocument';
import SocialMedia from './SocialMedia';
import { SocialErrorBanner } from './SocialNotice';
import SocialOverrides from './SocialOverrides';
import SocialPreview from './SocialPreview';
import SocialResults from './SocialResults';
import styles from './social.module.css';

function draftInput(post?: SocialPost): SocialDraftInput {
  return post ? { title: post.title, content_type: post.content_type, document: post.document, references: post.references } : { title: '', content_type: 'announcement', document: emptyDocument(), references: [] };
}
function dispatchStarted(post?: SocialPost) {
  return post?.targets.some(t => ['dispatching', 'processing', 'retry_wait', 'reconciling', 'published', 'failed', 'outcome_unknown'].includes(t.state)) ?? false;
}

export default function SocialComposer({ initialPost, accounts, accountsAvailable = true, system, onSaved, onDirtyChange }: { initialPost?: SocialPost; accounts: SocialAccount[]; accountsAvailable?: boolean; system?: SocialSystemStatus; onSaved?: (post: SocialPost) => void; onDirtyChange?: (dirty: boolean) => void }) {
  const [post, setPost] = useState(initialPost);
  const [input, setInput] = useState(() => draftInput(initialPost));
  const [hashtagText, setHashtagText] = useState(initialPost?.document.master.hashtags.join(' ') ?? '');
  const [dirty, setDirty] = useState(false);
  const [activeAccount, setActiveAccount] = useState(initialPost?.document.targets[0]?.account_id ?? '');
  const [validation, setValidation] = useState<{ version: number; value: SocialValidation }>();
  const [error, setError] = useState<SocialApiError>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [attested, setAttested] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [resumeReason, setResumeReason] = useState('');
  const [discard, setDiscard] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [localTime, setLocalTime] = useState('');
  const [timezone, setTimezone] = useState('Africa/Nairobi');
  const [offsetChoice, setOffsetChoice] = useState('');
  const [mobilePanel, setMobilePanel] = useState<'editor' | 'preview'>('editor');
  const [isMobile, setIsMobile] = useState(false);
  const mutation = useSocialMutation();
  const live = useSocialPost(post?.id);
  const latestPost = live.data && (!initialPost || live.data.version >= initialPost.version) ? live.data : initialPost;
  const effectivePost = latestPost && post && latestPost.version >= post.version ? latestPost : post;
  const delivery = useSocialDeliveryStatus(effectivePost);
  const currentPublication = effectivePost?.publication;
  const authorizationMatches = !!currentPublication && effectivePost?.editorial_state === 'approved' && currentPublication.revision_id === post?.revision_id && effectivePost.targets.length === input.document.targets.length && effectivePost.targets.length > 0 && new Set(effectivePost.targets.map(t => t.id)).size === effectivePost.targets.length && input.document.targets.every(selected => effectivePost.targets.filter(t => t.account_id === selected.account_id && t.platform === accounts.find(a => a.id === selected.account_id)?.platform).length === 1);
  const readyAuthorization = authorizationMatches && !currentPublication?.scheduled_for && effectivePost!.targets.every(t => t.state === 'ready');
  const cancelledAuthorization = authorizationMatches && effectivePost!.targets.every(t => t.state === 'cancelled');
  const civil = useMemo(() => resolveCivilTime(localTime, timezone), [localTime, timezone]);
  const selectedTime = civil.candidates.length === 1 ? civil.candidates[0] : civil.candidates.find(c => c.offset === offsetChoice);
  const stale = !!(latestPost && post && latestPost.version > post.version);
  const locked = dispatchStarted(latestPost) || dispatchStarted(post) || post?.editorial_state === 'archived';
  const target = input.document.targets.find(t => t.account_id === activeAccount);
  const account = accounts.find(a => a.id === target?.account_id);
  const valid = !dirty && !stale && !!post && validation?.version === post.version ? validation.value : undefined;
  // Never accept a valid=true envelope that omits/duplicates a selected destination.
  const selectedIds = input.document.targets.map(t => t.account_id);
  const distinctSelection = new Set(selectedIds).size === selectedIds.length;
  const hasContentChanges = !post || draftFingerprint(post) !== draftFingerprint(input);
  const allValid = !!valid?.valid && distinctSelection && input.document.targets.length > 0 && valid.errors.length === 0 && valid.targets.length === input.document.targets.length && input.document.targets.every(t => {
    const connected = accounts.find(a => a.id === t.account_id);
    const content = resolveContent(input.document.master, t);
    return !!connected && connected.publishing_enabled && connected.connection_state === 'connected' && valid.targets.filter(v => {
      const preview = v.resolved_preview;
      return v.account_id === t.account_id && v.platform === connected.platform && v.valid && v.errors.length === 0 && preview && preview.account_id === t.account_id && preview.platform === connected.platform && preview.format === t.format && preview.text === content.text && preview.link === content.link && JSON.stringify(preview.hashtags) === JSON.stringify(content.hashtags) && preview.assets.length === content.media.length && preview.assets.every((asset, i) => asset.asset_id === content.media[i].asset_id && asset.caption_asset_id === content.media[i].caption_asset_id && (content.media[i].alt_text == null || asset.alt_text === content.media[i].alt_text));
    }).length === 1;
  });
  const warnings = valid ? [...valid.warnings, ...valid.targets.flatMap(t => t.warnings)] : [];
  const warningCodes = Array.from(new Set(warnings.map(w => w.code)));
  const warningsAccepted = warningCodes.every(code => acknowledged.includes(code));
  const publicationGates = !busy && !locked && accountsAvailable && system?.publishing_enabled === true && allValid && warningsAccepted && ['draft', 'pending_review', 'approved'].includes(post?.editorial_state ?? '');
  const canPublish = publicationGates && (!currentPublication || readyAuthorization);
  const canResume = publicationGates && cancelledAuthorization && !!resumeReason.trim();
  const canSubmit = !busy && !locked && !stale && (!post || hasContentChanges || ['draft', 'rejected'].includes(post.editorial_state));

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 600px)');
    const update = () => setIsMobile(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    const linkGuard = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest('a') : null;
      if (!link || link.target === '_blank' || link.hasAttribute('download') || !link.href || event.defaultPrevented) return;
      if (new URL(link.href).pathname !== window.location.pathname && !window.confirm('This draft has unsaved edits. Leave without saving?')) event.preventDefault();
    };
    window.addEventListener('beforeunload', beforeUnload); document.addEventListener('click', linkGuard, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', linkGuard, true); };
  }, [dirty]);

  function edit(next: SocialDraftInput) { setInput(next); setDirty(true); setValidation(undefined); setAcknowledged([]); setAttested(false); setDiscard(false); setError(undefined); setMessage(''); }
  function fieldIssueProps(field: string) {
    const invalid = error?.fieldErrors.some(issue => issue.field === field || issue.field.endsWith(`.${field}`));
    return { 'aria-invalid': invalid || undefined, 'aria-describedby': invalid ? 'social-command-error' : undefined };
  }
  function changeTarget(next: DocumentTarget) { edit({ ...input, document: { ...input.document, targets: input.document.targets.map(t => t.account_id === next.account_id ? next : t) } }); }
  function select(id: string, checked: boolean) {
    const targets = checked ? [...input.document.targets, { account_id: id, format: 'text' as const, overrides: {} }] : input.document.targets.filter(t => t.account_id !== id);
    edit({ ...input, document: { ...input.document, targets } });
    if (checked) setActiveAccount(id); else if (activeAccount === id) setActiveAccount(targets[0]?.account_id ?? '');
  }
  function adopt(saved: SocialPost) {
    setPost(saved); setInput(draftInput(saved)); setDirty(false); setValidation(undefined); setAcknowledged([]); setAttested(false); setDiscard(false);
    setHashtagText(saved.document.master.hashtags.join(' '));
    if (!saved.document.targets.some(t => t.account_id === activeAccount)) setActiveAccount(saved.document.targets[0]?.account_id ?? '');
  }
  async function save(): Promise<SocialPost> {
    if (post && !hasContentChanges) { if (dirty) adopt(post); return post; }
    const saved = await mutation.run(post ? `/posts/${encodeURIComponent(post.id)}` : '/posts', post ? { ...input, expected_version: post.version } : input, value => {
      const result = decodePost(value);
      if (post && (result.id !== post.id || result.version <= post.version || result.revision_id === post.revision_id)) throw new SocialApiError('INVALID_RESPONSE', 'The save did not confirm a new revision of this post. Your local edits remain here; refresh before continuing.');
      if (draftFingerprint(result) !== draftFingerprint(input)) throw new SocialApiError('INVALID_RESPONSE', 'The saved content differs from the submitted draft. Your local edits remain here; no destination or content has been silently discarded.');
      if (!post && (result.origin_type !== 'manual' || result.editorial_state !== 'draft' || result.publication || result.targets.length)) throw new SocialApiError('INVALID_RESPONSE', 'The create response did not confirm an unpublished manual draft. Refresh before continuing.');
      return result;
    }, { method: post ? 'patch' : 'post', postId: post?.id });
    adopt(saved); return saved;
  }
  async function perform(action: () => Promise<void>) {
    if (running.current) return;
    running.current = true; setBusy(true); setError(undefined); setMessage('');
    try { await action(); } catch (e) {
      const failure = toSocialError(e);
      setError(failure);
      if (['VERSION_CONFLICT', 'TARGET_VALIDATION_FAILED', 'PUBLISHING_PAUSED', 'ACCOUNT_UNAVAILABLE', 'INVALID_RESPONSE'].includes(failure.code)) {
        setValidation(undefined); setAcknowledged([]);
      }
    } finally { running.current = false; setBusy(false); }
  }
  async function validate() {
    await perform(async () => {
      const saved = !post || dirty ? await save() : post;
      const result = await socialApi.validate(saved.id, saved.version);
      setValidation({ version: saved.version, value: result }); setAcknowledged([]);
      setMessage(result.valid ? 'Saved revision validated. Review every destination and any warnings before publishing.' : 'Saved draft. Selected destinations need attention before publication.');
    });
  }
  async function publish(scheduled: boolean) {
    if (!post || !canPublish) return;
    await perform(async () => {
      const body: PublishInput = { expected_version: post.version, revision_id: post.revision_id, acknowledged_warning_codes: acknowledged, ...(attested ? { review_attestation: { facts_checked: true, sources_checked: true } } : {}) };
      if (scheduled && (!selectedTime || Date.parse(selectedTime.utc) <= Date.now())) throw new SocialApiError('INVALID_SCHEDULE_TIME', 'Choose a future, unambiguous schedule time.');
      const result = await mutation.run(`/posts/${encodeURIComponent(post.id)}/${scheduled ? 'schedule' : 'publish'}`, scheduled ? { ...body, schedule: { local_time: localTime.length === 16 ? `${localTime}:00` : localTime, timezone, utc_offset: selectedTime!.offset } } : body, value => {
        return acceptedReceipt(value, scheduled ? selectedTime!.utc : undefined);
      }, { postId: post.id });
      setValidation(undefined); setMessage(`${scheduled ? 'Schedule' : 'Publication'} accepted for ${result.targets.length} destination(s). The worker reports each delivery separately; nothing is marked published here.`);
    });
  }
  function acceptedReceipt(value: unknown, expectedSchedule?: string) {
    const receipt = decodePublication(value);
    const authorizedTargets = currentPublication ? effectivePost?.targets : undefined;
    const stableAuthorization = !currentPublication || receipt.publication_id === currentPublication.id && !!authorizedTargets && receipt.targets.every(t => authorizedTargets.filter(authorized => authorized.id === t.id && authorized.account_id === t.account_id && authorized.platform === t.platform).length === 1);
    if (!post || receipt.post_id !== post.id || receipt.targets.length !== selectedIds.length || new Set(receipt.targets.map(t => t.id)).size !== selectedIds.length || !selectedIds.every(id => receipt.targets.filter(t => t.account_id === id && t.platform === accounts.find(a => a.id === id)?.platform && t.status === 'queued').length === 1) || !stableAuthorization || !Number.isFinite(Date.parse(receipt.scheduled_for ?? '')) || (expectedSchedule && Date.parse(receipt.scheduled_for!) !== Date.parse(expectedSchedule))) throw new SocialApiError('INVALID_RESPONSE', 'The publication receipt did not confirm the exact post, authorization, schedule and every selected destination. Refresh results before continuing; the original command key is preserved.');
    return receipt;
  }
  async function resume() {
    if (!post || !canResume) return;
    await perform(async () => {
      const originalDue = currentPublication?.scheduled_for ? Date.parse(currentPublication.scheduled_for) : undefined;
      const body = { expected_version: post.version, revision_id: post.revision_id, acknowledged_warning_codes: acknowledged, reason: resumeReason.trim(), ...(attested ? { review_attestation: { facts_checked: true, sources_checked: true } } : {}) };
      const result = await mutation.run(`/posts/${encodeURIComponent(post.id)}/resume`, body, value => {
        const receipt = acceptedReceipt(value);
        const confirmedAt = Date.now(), resumedDue = Date.parse(receipt.scheduled_for!);
        // Target work uses max(now, original due), while the receipt may retain
        // the original schedule. A future schedule can expire during the call.
        if (originalDue !== undefined && (!Number.isFinite(originalDue) || (originalDue > confirmedAt ? resumedDue !== originalDue : resumedDue < originalDue || resumedDue > confirmedAt + 5_000))) throw new SocialApiError('INVALID_RESPONSE', 'The resume receipt changed the original future schedule or returned an unrelated overdue due time. The original command key was preserved.');
        return receipt;
      }, { postId: post.id });
      setValidation(undefined); setMessage(`Resume accepted for ${result.targets.length} destination(s). Review each delivery result; nothing is marked published here.`);
    });
  }
  async function editorial(action: 'submit' | 'approve' | 'reject' | 'cancel' | 'duplicate') {
    if (action === 'submit' && !canSubmit) return;
    await perform(async () => {
      const saved = !post || dirty ? await save() : post;
      const body = { expected_version: saved.version, ...(action === 'approve' ? { revision_id: saved.revision_id, ...(attested ? { review_attestation: { facts_checked: true, sources_checked: true } } : {}) } : {}), ...(action === 'reject' ? { reason: rejectReason } : {}) };
      const result = await mutation.run(`/posts/${encodeURIComponent(saved.id)}/${action}`, body, value => {
        const detail = decodePost(value);
        if (action !== 'duplicate' && detail.id !== saved.id) throw new SocialApiError('INVALID_RESPONSE', 'The command response belongs to another post. Your draft and the original command key were preserved.');
        return detail;
      }, { postId: saved.id });
      if (action === 'duplicate') { onSaved?.(result); if (!onSaved) window.location.assign(`/admin/social/${result.id}`); }
      else adopt(result);
      setMessage(action === 'cancel' ? 'Cancellation recorded. Accepted or in-flight remote requests may still complete; review each result.' : action === 'approve' ? 'This exact revision is approved. Publication is a separate command.' : action === 'submit' ? 'Draft submitted for human review.' : action === 'reject' ? 'Draft rejected; the reason is recorded.' : 'New manual draft created.');
    });
  }
  const latestResults = latestPost && post && latestPost.version >= post.version ? latestPost.targets : post?.targets ?? [];
  // PageShell animates its content with a transform. A body portal keeps mobile
  // fixed controls attached to the viewport instead of that containing block.
  const primaryActions = !locked && <div className={`${styles.actionBar} ${isMobile ? styles.floatingActions : ''}`}><button type='button' className={styles.button} disabled={busy || stale || (!!post && !dirty)} onClick={() => perform(async () => { const saved = await save(); setMessage(hasContentChanges ? 'Draft saved. Nothing has been queued for publication.' : 'Saved content is unchanged. The current revision and authorization were kept.'); if (!initialPost) onSaved?.(saved); })}>Save draft</button><button type='button' className={`${styles.button} ${styles.primary}`} disabled={!canPublish} onClick={() => publish(false)}>Publish now</button></div>;

  return <article className={styles.editor} aria-label='Social post composer'>
    <div className={styles.editorHeading}><div><span className={styles.tag}>{post?.origin_type ?? 'Manual'} · {input.content_type || 'Content'}</span><h2>{post ? input.title || 'Untitled draft' : 'Create a manual post'}</h2></div><span className={styles.badge}>{busy ? 'Saving / checking…' : dirty ? 'Unsaved edits' : post ? `${post.editorial_state.replaceAll('_', ' ')} · revision ${post.version}` : 'Draft · not saved'}</span></div>
    <div className={styles.editorBody}>
      {error && <SocialErrorBanner error={error} id='social-command-error' />}
      {live.error && <SocialErrorBanner error={live.error} onRetry={() => live.refetch()} />}
      {delivery.error && <SocialErrorBanner error={delivery.error} onRetry={() => delivery.refetch()} />}
      {message && <p className={styles.success} role='status'>{message}</p>}
      {stale && <p className={styles.notice} role='alert'>A newer revision is available (version {latestPost?.version}). Your local edits are preserved. Load the current revision before publishing.</p>}
      {(stale || error?.code === 'VERSION_CONFLICT') && <div className={styles.fields}>{dirty && <label className={styles.reviewCheck}><input type='checkbox' checked={discard} onChange={e => setDiscard(e.target.checked)} />Discard my local edits when loading the current revision</label>}<button type='button' className={styles.button} disabled={busy || (dirty && !discard)} onClick={() => perform(async () => { if (post) adopt(await socialApi.post(post.id)); setMessage('Current revision loaded. Review it before saving or publishing.'); })}>Load current revision</button></div>}
      {locked && <p className={styles.notice}>This revision has begun publishing or is archived. Content is locked. Review the results or duplicate it as a new manual draft.</p>}
      {currentPublication?.scheduled_for && <p className={styles.notice}>Scheduled for {currentPublication.scheduled_for} (UTC). Editing unsent content creates a new revision and requires approval again.</p>}
      <div className={`${styles.tabs} ${styles.mobileSwitch}`} aria-label='Mobile workspace view'><button type='button' aria-pressed={mobilePanel === 'editor'} onClick={() => setMobilePanel('editor')}>Editor</button><button type='button' aria-pressed={mobilePanel === 'preview'} onClick={() => setMobilePanel('preview')}>Preview</button></div>
      <fieldset disabled={busy} className={styles.destinations}>
        <div className={styles.composerGrid}>
          <fieldset disabled={locked} className={`${styles.destinations} ${styles.fields} ${mobilePanel === 'preview' ? styles.mobileHidden : ''}`}>
            <div className={styles.twoFields}><label>Internal title<input value={input.title} {...fieldIssueProps('title')} onChange={e => edit({ ...input, title: e.target.value })} /></label><label>Content type<input value={input.content_type} {...fieldIssueProps('content_type')} onChange={e => edit({ ...input, content_type: e.target.value })} /></label></div>
            <h3>Master content</h3>
            <label>Master text<textarea rows={7} value={input.document.master.text} {...fieldIssueProps('text')} onChange={e => edit({ ...input, document: { ...input.document, master: { ...input.document.master, text: e.target.value } } })} /></label>
            <p className={styles.muted}>{Array.from(input.document.master.text).length} characters · local count is provisional</p>
            <label>Website URL<input type='url' value={input.document.master.link ?? ''} {...fieldIssueProps('link')} onChange={e => edit({ ...input, document: { ...input.document, master: { ...input.document.master, link: e.target.value || null } } })} /></label>
            <label>Master hashtags<input value={hashtagText} {...fieldIssueProps('hashtags')} onChange={e => { setHashtagText(e.target.value); edit({ ...input, document: { ...input.document, master: { ...input.document.master, hashtags: e.target.value.split(/\s+/).filter(Boolean) } } }); }} /><span className={styles.muted}>Separate hashtags with spaces. Content is never shortened automatically.</span></label>
            <details className={styles.evidence} open><summary>Sources & factual review</summary><div><p className={styles.muted}>Manual content is first class. Sources are reference links; they are not automatically fetched or verified.</p>{input.references.map((reference, index) => <div className={styles.fields} key={index}><label>Source URL {index + 1}<input type='url' value={reference.url} {...fieldIssueProps(`references.${index}.url`)} onChange={e => edit({ ...input, references: input.references.map((r, i) => i === index ? { ...r, url: e.target.value } : r) })} /></label><label>Source label {index + 1}<input value={reference.label ?? ''} {...fieldIssueProps(`references.${index}.label`)} onChange={e => edit({ ...input, references: input.references.map((r, i) => i === index ? { ...r, label: e.target.value } : r) })} /></label>{httpsUrl(reference.url) && <a href={httpsUrl(reference.url)} target='_blank' rel='noopener noreferrer'>Open source {index + 1}</a>}<button type='button' className={styles.button} onClick={() => edit({ ...input, references: input.references.filter((_, i) => i !== index) })}>Remove source {index + 1}</button></div>)}<button type='button' className={styles.button} onClick={() => edit({ ...input, references: [...input.references, { url: '' }] })}>Add source reference</button></div></details>
            <h3>Master media</h3><SocialMedia label='Master' media={input.document.master.media} onChange={media => edit({ ...input, document: { ...input.document, master: { ...input.document.master, media } } })} />
            <fieldset className={styles.destinations}><legend>Publish to connected accounts</legend>
              {!accountsAvailable ? <p className={styles.notice}>Connected accounts could not be loaded. Saved selections are preserved; publishing is unavailable until accounts can be verified.</p> : !accounts.length && <p className={styles.empty}>No connected accounts. You can save a manual draft. Account connection is unavailable in this batch.</p>}
              <div className={styles.accounts}>{accounts.map(a => <label className={styles.account} key={a.id}><input type='checkbox' checked={input.document.targets.some(t => t.account_id === a.id)} onChange={e => select(a.id, e.target.checked)} /><span>{platformLabels[a.platform]} · {a.display_name}<small>{a.handle ?? 'Handle unavailable'} · {a.connection_state}{!a.publishing_enabled ? ' · publishing disabled' : ''}</small></span></label>)}</div>
              {input.document.targets.filter(t => !accounts.some(a => a.id === t.account_id)).map(t => <label key={t.account_id} className={styles.account}><input type='checkbox' checked onChange={() => select(t.account_id, false)} /><span>Unavailable account · {t.account_id}<small>Selection retained. Uncheck to explicitly remove it.</small></span></label>)}
            </fieldset>
          </fieldset>
          <div className={`${styles.fields} ${mobilePanel === 'editor' ? styles.mobileHidden : ''}`}>
            <h3>Account preview & overrides</h3>
            <div className={styles.tabs} aria-label='Account preview tabs'>{input.document.targets.map((t, index) => { const a = accounts.find(a => a.id === t.account_id); return <button type='button' key={`${t.account_id}-${index}`} aria-pressed={activeAccount === t.account_id} onClick={() => setActiveAccount(t.account_id)}>{a ? `${platformLabels[a.platform]} · ${a.display_name}` : 'Unavailable account'}</button>; })}</div>
            <SocialPreview master={input.document.master} target={target} account={account} validation={valid?.targets.find(t => t.account_id === target?.account_id)} />
            {target && <fieldset disabled={locked} className={`${styles.destinations} ${styles.fields}`}><label>Account format<select value={target.format} onChange={e => changeTarget({ ...target, format: e.target.value as DocumentTarget['format'] })}>{(['text', 'image', 'carousel', 'video', 'reel'] as const).map(format => <option key={format} value={format}>{format}{supportedFormats(account).length && !supportedFormats(account).includes(format) ? ' · unsupported' : ''}</option>)}</select></label>{targetHints(input.document.master, target, account).map((hint, index) => <p className={styles.notice} key={index}>{hint}</p>)}<p className={styles.muted}>{Array.from(resolveContent(input.document.master, target).text).length} characters · provisional account count</p><SocialOverrides master={input.document.master} target={target} onChange={changeTarget} /></fieldset>}
          </div>
        </div>
      </fieldset>
      {valid && <section className={styles.validation} aria-label='Backend validation'><h3>Saved revision validation</h3><p>{allValid ? 'All selected destinations passed.' : 'Publication blocked. Every selected destination must pass.'} · {valid.rules_version}</p>{valid.errors.map((issue, i) => <p className={styles.notice} key={i}>{issue.message}</p>)}{valid.targets.map((t, index) => <div className={styles.validationTarget} key={`${t.account_id}-${index}`}><strong>{t.platform ? platformLabels[t.platform] : 'Unknown platform'} · {accounts.find(a => a.id === t.account_id)?.display_name ?? 'Unavailable account'} · {t.valid ? 'Valid' : 'Needs attention'}</strong><ul>{[...t.errors, ...t.warnings].map((issue, i) => <li key={i}>{issue.message}</li>)}</ul></div>)}{warningCodes.map(code => <label className={styles.reviewCheck} key={code}><input type='checkbox' checked={acknowledged.includes(code)} disabled={busy} onChange={e => setAcknowledged(e.target.checked ? [...acknowledged, code] : acknowledged.filter(c => c !== code))} />Acknowledge {code}: {warnings.filter(w => w.code === code).map(w => w.message).join(' ')}</label>)}</section>}
      {post && <><div className={styles.actions}><button type='button' className={styles.button} disabled={busy || live.isFetching} onClick={() => live.refetch()}>Refresh revision & results</button></div><SocialResults targets={latestResults} accounts={accounts} postId={post.id} />{effectivePost?.cancellation && <p className={styles.notice}>{effectivePost.cancellation.message} · {effectivePost.cancellation.in_flight_target_ids.length} in-flight destination(s) reported.</p>}</>}
    </div>
    <div className={styles.footer}>
      <p className={styles.muted}>{system ? system.publishing_enabled ? 'Publishing enabled. Backend gates are checked again for every command.' : 'Publishing is paused. Draft saving and review remain available.' : 'Publishing status unavailable. Draft saving remains available.'}</p>
      {!locked && <><label className={styles.reviewCheck}><input type='checkbox' checked={attested} disabled={busy} onChange={e => setAttested(e.target.checked)} />I checked the facts and sources. This attestation is required when the server identifies sensitive content.</label><div className={styles.actions}><button type='button' className={styles.button} disabled={busy || stale} onClick={validate}>Save & validate</button><button type='button' className={styles.button} disabled={!canSubmit} onClick={() => editorial('submit')}>Submit for review</button></div>
        {!allValid && <p className={styles.muted}>Save & validate the current revision to enable publication. No invalid destination will be silently omitted.</p>}
        <div className={styles.actions}><button type='button' className={styles.button} disabled={busy || (!!currentPublication && !readyAuthorization)} aria-expanded={scheduleOpen} onClick={() => setScheduleOpen(!scheduleOpen)}>Schedule</button>{post?.editorial_state === 'pending_review' && <button type='button' className={styles.button} disabled={busy || !allValid} onClick={() => editorial('approve')}>Approve revision</button>}</div>
        {scheduleOpen && <div className={styles.schedule}><h3>One schedule for all selected accounts</h3><div className={styles.twoFields}><label>Local publish time<input type='datetime-local' value={localTime} disabled={busy} onChange={e => { setLocalTime(e.target.value); setOffsetChoice(''); }} /></label><label>IANA timezone<input value={timezone} disabled={busy} onChange={e => { setTimezone(e.target.value); setOffsetChoice(''); }} /></label></div>{civil.error && <p className={styles.notice} role='alert'>{civil.error}</p>}{civil.candidates.length > 1 && <label>UTC offset (this local time occurs twice)<select value={offsetChoice} disabled={busy} onChange={e => setOffsetChoice(e.target.value)}><option value=''>Choose the intended occurrence</option>{civil.candidates.map(c => <option key={c.offset} value={c.offset}>{c.offset} · {c.utc}</option>)}</select></label>}{selectedTime && <p>UTC preview: {selectedTime.utc} · offset {selectedTime.offset}</p>}<button type='button' className={`${styles.button} ${styles.primary}`} disabled={!canPublish || !selectedTime || Date.parse(selectedTime.utc) <= Date.now()} onClick={() => publish(true)}>Confirm schedule</button><p className={styles.muted}>The server rejects invalid, ambiguous or past times. A scheduled target still requires publishing gates to be enabled when due.</p></div>}
        {post?.editorial_state === 'pending_review' && <div className={styles.fields}><label>Reason to reject<input value={rejectReason} disabled={busy} onChange={e => setRejectReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={busy || stale || dirty || !rejectReason.trim()} onClick={() => editorial('reject')}>Reject draft</button></div>}
        {cancelledAuthorization && <div className={styles.fields}><label>Reason to resume<input value={resumeReason} disabled={busy} onChange={e => setResumeReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={!canResume} onClick={resume}>Resume unsent deliveries</button><p className={styles.muted}>The server checks that every destination is unchanged, unsent and within its original deadlines. Future schedules are kept; expired or attempted deliveries require a new draft.</p></div>}
      </>}
      {post && <div className={styles.actions}>{currentPublication && <button type='button' className={styles.button} disabled={busy || stale || dirty} onClick={() => editorial('cancel')}>Cancel unsent deliveries</button>}<button type='button' className={styles.button} disabled={busy || dirty || stale} onClick={() => editorial('duplicate')}>Duplicate as new manual draft</button></div>}
    </div>
    {isMobile ? createPortal(<div className={styles.workspace} data-social-actions-portal>{primaryActions}</div>, document.body) : primaryActions}
  </article>;
}
