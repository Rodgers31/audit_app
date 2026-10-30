'use client';

import GeneratedEvidence from './GeneratedEvidence';
import { useAuth } from '@/lib/auth/AuthProvider';
import { consumeApprovedTraversal, useUnsavedHistoryGuard } from '@/lib/navigation/historyGuard';
import useComposerErrors from './useComposerErrors';
import SocialArchiveControls from './SocialArchiveControls';

import { decodePost, decodePublication, DocumentTarget, PublishInput, SocialAccount, SocialApiError, SocialDraftInput, SocialPost, SocialSystemStatus, SocialValidation, socialApi, toSocialError } from '@/lib/api/social';
import { useSocialDeliveryStatus, useSocialMutation, useSocialPost } from '@/lib/hooks/useSocial';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { draftFingerprint, emptyDocument, httpsUrl, postDestinationIssue, platformLabels, resolveCivilTime, resolveContent, supportedFormats, targetHints } from './socialDocument';
import SocialMedia from './SocialMedia';
import { automaticMediaFormats } from './automaticMediaFormat';
import type { MediaAsset } from '@/lib/api/socialMedia';
import SocialScheduleControls from './SocialScheduleControls';
import { SocialErrorBanner } from './SocialNotice';
import TikTokControls from './TikTokControls';
import { clearChangedTikTokConfirmations } from './tiktokConsent';
import SocialOverrides from './SocialOverrides';
import SocialPreview from './SocialPreview';
import SocialResults from './SocialResults';
import SocialDeliveryHistory from './SocialDeliveryHistory';
import styles from './social.module.css';

function draftInput(post?: SocialPost): SocialDraftInput {
  return post ? { title: post.title, content_type: post.content_type, document: post.document, references: post.references } : { title: '', content_type: 'announcement', document: emptyDocument(), references: [] };
}
function dispatchStarted(post?: SocialPost) {
  return post?.targets.some(t => ['dispatching', 'processing', 'retry_wait', 'reconciling', 'published', 'failed', 'outcome_unknown'].includes(t.state)) ?? false;
}

export default function SocialComposer({ initialPost, accounts, accountsAvailable = true, system, onSaved, onDirtyChange }: { initialPost?: SocialPost; accounts: SocialAccount[]; accountsAvailable?: boolean; system?: SocialSystemStatus; onSaved?: (post: SocialPost) => void; onDirtyChange?: (dirty: boolean) => void }) {
  const { user } = useAuth();
  const actor = user?.id;
  const currentActor = useRef(actor);
  currentActor.current = actor;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const contextIsCurrent = () => mounted.current && currentActor.current === actor;
  const [post, setPost] = useState(initialPost);
  const [input, setInput] = useState(() => draftInput(initialPost));
  const [hashtagText, setHashtagText] = useState(initialPost?.document.master.hashtags.join(' ') ?? '');
  const [dirty, setDirty] = useState(false);
  const confirmNavigationClick = useUnsavedHistoryGuard(dirty, input);
  const [activeAccount, setActiveAccount] = useState(initialPost?.document.targets[0]?.account_id ?? '');
  const [validation, setValidation] = useState<{ version: number; value: SocialValidation }>();
  const [error, setError] = useState<SocialApiError>();
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const running = useRef(false);
  const composerContext = useId();
  const mediaOperations = useRef(new Set<string>());
  const [mediaPending, setMediaPending] = useState(false);
  const archiveRunning = useRef(false);
  const [archivePending, setArchivePending] = useState(false);
  function archiveBusyChanged(active: boolean) { archiveRunning.current = active; setArchivePending(active); }
  const commandBusy = busy || mediaPending || archivePending;
  function mediaBusyChanged(scope: string, active: boolean) {
    if (active) mediaOperations.current.add(scope); else mediaOperations.current.delete(scope);
    setMediaPending(mediaOperations.current.size > 0);
  }
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [attested, setAttested] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [resumeReason, setResumeReason] = useState('');
  const [discard, setDiscard] = useState(false);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [localTime, setLocalTime] = useState('');
  const [timezone, setTimezone] = useState('Africa/Nairobi');
  const [offsetChoice, setOffsetChoice] = useState('');
  const [mobilePanel, setMobilePanel] = useState<'editor' | 'preview'>(initialPost?.origin_type === 'generated' ? 'preview' : 'editor');
  const autoAttempt = useRef('');
  const mediaMimeTypes = useRef(new Map<string, string>());
  const [isMobile, setIsMobile] = useState(false);
  const {editorRef,errorId,fieldIssueProps,fieldLinks,selectField}=useComposerErrors(error,input.document.targets,activeAccount,setActiveAccount,mobilePanel,setMobilePanel);
  const mutation = useSocialMutation();
  const live = useSocialPost(post?.id);
  const latestPost = live.data && (!initialPost || live.data.version >= initialPost.version) ? live.data : initialPost;
  const effectivePost = latestPost && post && latestPost.version >= post.version ? latestPost : post;
  const delivery = useSocialDeliveryStatus(effectivePost);
  const currentPublication = effectivePost?.publication;
  const authorizationMatches = !!currentPublication && effectivePost?.editorial_state === 'approved' && currentPublication.approved_by !== null && currentPublication.revision_id === post?.revision_id && effectivePost.targets.length === input.document.targets.length && effectivePost.targets.length > 0 && new Set(effectivePost.targets.map(t => t.id)).size === effectivePost.targets.length && input.document.targets.every(selected => effectivePost.targets.filter(t => t.account_id === selected.account_id && t.platform === accounts.find(a => a.id === selected.account_id)?.platform).length === 1);
  const readyAuthorization = authorizationMatches && !currentPublication?.scheduled_for && effectivePost!.targets.every(t => t.state === 'ready');
  const cancelledAuthorization = authorizationMatches && effectivePost!.targets.every(t => t.state === 'cancelled');
  const civil = useMemo(() => resolveCivilTime(localTime, timezone), [localTime, timezone]);
  const selectedTime = civil.candidates.length === 1 ? civil.candidates[0] : civil.candidates.find(c => c.offset === offsetChoice);
  const stale = !!(latestPost && post && latestPost.version > post.version);
  const locked = dispatchStarted(latestPost) || dispatchStarted(post) || effectivePost?.editorial_state === 'archived';
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
    return !postDestinationIssue(content) && !!connected && connected.publishing_enabled && connected.connection_state === 'connected' && valid.targets.filter(v => {
      const preview = v.resolved_preview;
      return v.account_id === t.account_id && v.platform === connected.platform && v.valid && v.errors.length === 0 && preview && preview.account_id === t.account_id && preview.platform === connected.platform && preview.format === t.format && preview.text === content.text && preview.link === content.link && JSON.stringify(preview.hashtags) === JSON.stringify(content.hashtags) && preview.assets.length === content.media.length && preview.assets.every((asset, i) => asset.asset_id === content.media[i].asset_id && asset.caption_asset_id === content.media[i].caption_asset_id && (content.media[i].alt_text == null || asset.alt_text === content.media[i].alt_text));
    }).length === 1;
  });
  const warnings = valid ? [...valid.warnings, ...valid.targets.flatMap(t => t.warnings)] : [];
  const warningCodes = Array.from(new Set(warnings.map(w => w.code)));
  const warningsAccepted = warningCodes.every(code => acknowledged.includes(code));
  const publicationGates = !commandBusy && !locked && accountsAvailable && system?.publishing_enabled === true && allValid && warningsAccepted && ['draft', 'pending_review', 'approved'].includes(post?.editorial_state ?? '');
  const canPublish = publicationGates && (!currentPublication || readyAuthorization);
  const canResume = publicationGates && cancelledAuthorization && !!resumeReason.trim();
  const canSubmit = !commandBusy && !locked && !stale && (!post || hasContentChanges || ['draft', 'rejected'].includes(post.editorial_state));

  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  useEffect(() => {
    const media = window.matchMedia('(max-width: 600px)');
    const update = () => setIsMobile(media.matches);
    update(); media.addEventListener('change', update);
    return () => media.removeEventListener('change', update);
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { if (consumeApprovedTraversal()) return; event.preventDefault(); event.returnValue = ''; };
    const linkGuard = (event: MouseEvent) => {
      const link = event.target instanceof Element ? event.target.closest('a') : null;
      if (!link || link.target === '_blank' || link.hasAttribute('download') || !link.href || event.defaultPrevented
          || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (new URL(link.href).pathname !== window.location.pathname) {
        if (!confirmNavigationClick(event)) event.preventDefault();
      }
    };
    window.addEventListener('beforeunload', beforeUnload); document.addEventListener('click', linkGuard, true);
    return () => { window.removeEventListener('beforeunload', beforeUnload); document.removeEventListener('click', linkGuard, true); };
  }, [dirty, confirmNavigationClick]);

  function edit(next: SocialDraftInput) { setInput(previous => clearChangedTikTokConfirmations(previous, next)); setDirty(true); setValidation(undefined); setAcknowledged([]); setAttested(false); setDiscard(false); setError(undefined); setMessage(''); }
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
    if (!contextIsCurrent()) throw new SocialApiError('ACCESS_DENIED', 'The review session changed. Refresh the current draft.');
    if (post && !hasContentChanges) { if (dirty) adopt(post); return post; }
    const submitted = { ...input, title: input.title.trim() || Array.from(input.document.master.text.trim().split(/\r?\n/)[0]).slice(0, 180).join('') || 'Untitled draft' };
    const saved = await mutation.run(post ? `/posts/${encodeURIComponent(post.id)}` : '/posts', post ? { ...submitted, expected_version: post.version } : submitted, value => {
      const result = decodePost(value);
      if (post && (result.id !== post.id || result.version <= post.version || result.revision_id === post.revision_id)) throw new SocialApiError('INVALID_RESPONSE', 'The save did not confirm a new revision of this post. Your local edits remain here; refresh before continuing.');
      if (draftFingerprint(result) !== draftFingerprint(submitted)) throw new SocialApiError('INVALID_RESPONSE', 'The saved content differs from the submitted draft. Your local edits remain here; no destination or content has been silently discarded.');
      if (!post && (result.origin_type !== 'manual' || result.editorial_state !== 'draft' || result.publication || result.targets.length)) throw new SocialApiError('INVALID_RESPONSE', 'The create response did not confirm an unpublished manual draft. Refresh before continuing.');
      return result;
    }, { method: post ? 'patch' : 'post', postId: post?.id });
    if (!contextIsCurrent()) throw new SocialApiError('ACCESS_DENIED', 'The review session changed. Refresh the current draft.');
    adopt(saved); return saved;
  }
  async function perform(action: () => Promise<void>) {
    if (running.current || archiveRunning.current || mediaOperations.current.size > 0) return;
    running.current = true; setBusy(true); setError(undefined); setMessage('');
    try { await action(); } catch (e) {
      if (!contextIsCurrent()) return;
      const failure = toSocialError(e);
      setError(failure);
      if (['VERSION_CONFLICT', 'TARGET_VALIDATION_FAILED', 'PUBLISHING_PAUSED', 'ACCOUNT_UNAVAILABLE', 'INVALID_RESPONSE'].includes(failure.code)) {
        setValidation(undefined); setAcknowledged([]);
      }
    } finally { running.current = false; if (contextIsCurrent()) setBusy(false); }
  }
  async function validate() {
    await perform(async () => {
      const saved = !post || dirty ? await save() : post;
      if (!contextIsCurrent()) return;
      const result = await socialApi.validate(saved.id, saved.version);
      if (!contextIsCurrent()) return;
      setValidation({ version: saved.version, value: result }); setAcknowledged([]);
      setMessage(result.valid ? 'Saved revision validated. Review every destination and any warnings before publishing.' : 'Saved draft. Selected destinations need attention before publication.');
    });
  }
  // Validation reads the exact saved revision. Generated edits/media are saved
  // after a short idle window; this never approves, schedules or publishes.
  const autoFingerprint = draftFingerprint(input);
  useEffect(() => {
    if (post?.origin_type !== 'generated' || locked || stale || commandBusy || !accountsAvailable) return;
    if (!dirty && validation?.version === post.version) return;
    const attempt = `${post.id}:${post.version}:${autoFingerprint}`;
    if (autoAttempt.current === attempt) return;
    const timer = setTimeout(() => {
      if (running.current || archiveRunning.current || mediaOperations.current.size) return;
      autoAttempt.current = attempt;
      void validate();
    }, dirty ? 750 : 0);
    return () => clearTimeout(timer);
    // validate captures this exact document/revision. Busy/attempt guards prevent loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [post?.id, post?.version, post?.origin_type, autoFingerprint, dirty, validation?.version, locked, stale, commandBusy, accountsAvailable]);

  function changeMasterMedia(media: SocialDraftInput['document']['master']['media'], selectedAsset?: MediaAsset) {
    if (selectedAsset?.mime_type) mediaMimeTypes.current.set(selectedAsset.id, selectedAsset.mime_type);
    const document = automaticMediaFormats({ ...input.document, master: { ...input.document.master, media } }, accounts, mediaMimeTypes.current);
    edit({ ...input, document });
  }

  async function prepareCopy() {
    if (!post || dirty) return;
    await perform(async () => {
      const result = await mutation.run(`/posts/${encodeURIComponent(post.id)}/prepare`, {
        expected_version: post.version, revision_id: post.revision_id, reason: 'Prepare current verified source copy, contextual hashtags and AuditGava destination.'
      }, value => {
        const prepared = decodePost(value);
        if (prepared.id !== post.id || prepared.version <= post.version || prepared.revision_id === post.revision_id || prepared.origin_type !== 'generated') throw new SocialApiError('INVALID_RESPONSE', 'The prepared draft response did not confirm a new revision. Refresh before continuing.');
        return prepared;
      }, { postId: post.id });
      adopt(result); setMessage('Copy, hashtags and website destination refreshed from the current verified source. Media is retained; review the new revision.');
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
  const primaryActions = !locked && <div className={`${styles.actionBar} ${isMobile && (dirty || !post) ? styles.floatingActions : ''}`}><button type='button' className={`${styles.button} ${dirty || !post ? styles.primary : ''}`} disabled={commandBusy || stale || (!!post && !dirty)} onClick={() => perform(async () => { const saved = await save(); setMessage(hasContentChanges ? 'Draft saved. Nothing has been queued for publication.' : 'Saved content is unchanged. The current revision and authorization were kept.'); if (!initialPost) onSaved?.(saved); })}>Save draft</button></div>;

  return <article ref={editorRef} className={styles.editor} aria-label='Social post composer'>
    <div className={styles.editorHeading}><div><span className={styles.tag}>{post?.origin_type === 'generated' ? 'Generated from source data' : 'Written manually'}</span><h2>{post ? input.title || 'Untitled draft' : 'Create a manual post'}</h2></div><span className={styles.badge}>{busy ? 'Saving / checking…' : dirty ? 'Unsaved edits' : post ? `${post.editorial_state.replaceAll('_', ' ')} · revision ${post.version}` : 'Draft · not saved'}</span></div>
    <div className={styles.editorBody}>
      {error && <SocialErrorBanner error={error} id={errorId} fieldLinks={fieldLinks} onFieldSelect={selectField} />}
      {live.error && <SocialErrorBanner error={live.error} onRetry={() => live.refetch()} />}
      {delivery.error && <SocialErrorBanner error={delivery.error} onRetry={() => delivery.refetch()} />}
      {message && <p className={styles.success} role='status'>{message}</p>}
      {stale && <p className={styles.notice} role='alert'>A newer revision is available (version {latestPost?.version}). Your local edits are preserved. Load the current revision before publishing.</p>}
      {(stale || error?.code === 'VERSION_CONFLICT') && <div className={styles.fields}>{dirty && <label className={styles.reviewCheck}><input type='checkbox' checked={discard} onChange={e => setDiscard(e.target.checked)} />Discard my local edits when loading the current revision</label>}<button type='button' className={styles.button} disabled={commandBusy || (dirty && !discard)} onClick={() => perform(async () => { if (post) adopt(await socialApi.post(post.id)); setMessage('Current revision loaded. Review it before saving or publishing.'); })}>Load current revision</button></div>}
      {locked && <p className={styles.notice}>This revision has begun publishing or is archived. Content is locked. Review the results or duplicate it as a new manual draft.</p>}
      {currentPublication && currentPublication.approved_by === null && <p className={styles.notice}>Authorized by an approved policy. Human schedule changes require a new reviewed revision.</p>}
      {currentPublication?.scheduled_for && <p className={styles.notice}>Scheduled for {currentPublication.scheduled_for} (UTC). Editing unsent content creates a new revision and requires approval again.</p>}
      <div className={`${styles.tabs} ${styles.mobileSwitch}`} aria-label='Mobile workspace view'><button type='button' aria-pressed={mobilePanel === 'editor'} onClick={() => setMobilePanel('editor')}>Editor</button><button type='button' aria-pressed={mobilePanel === 'preview'} onClick={() => setMobilePanel('preview')}>Preview</button></div>
      <fieldset disabled={busy || archivePending} className={styles.destinations}>
        {post?.origin_type === 'generated' && <section className={styles.fields} aria-label='Prepared post and optional media'>
          <p className={styles.muted}>Caption, relevant hashtags, website destination and source references are prepared. Add optional media, review each account preview and post when publishing is enabled. Changes save and validate automatically.</p>
          <section tabIndex={-1} {...fieldIssueProps('document.master.media')}><SocialMedia label='Master' contextKey={`${post.id}:master`} onBusyChange={active => mediaBusyChanged('master', active)} media={input.document.master.media} onChange={changeMasterMedia} /></section>
          <button type='button' className={styles.button} disabled={commandBusy || dirty || stale || locked} onClick={prepareCopy}>Refresh caption &amp; hashtags</button>
          <p className={styles.muted} role='status'>{busy ? 'Saving or checking this revision…' : dirty ? 'Waiting to save your changes…' : validation?.version === post.version ? 'This saved revision has been checked. Review any account holds or warnings below.' : 'Checking the saved revision…'}</p>
        </section>}
        <div className={styles.composerGrid}>
          <fieldset data-composer-panel='editor' disabled={locked} className={`${styles.destinations} ${styles.fields} ${mobilePanel === 'preview' ? styles.mobileHidden : ''}`}>
            <label>Post text<textarea rows={7} value={input.document.master.text} {...fieldIssueProps('document.master.text')} onChange={e => edit({ ...input, document: { ...input.document, master: { ...input.document.master, text: e.target.value } } })} /></label>
            <p className={styles.muted}>{Array.from(input.document.master.text).length} characters · local count is provisional</p>
            <label>Website URL<input type='url' value={input.document.master.link ?? ''} {...fieldIssueProps('document.master.link')} onChange={e => edit({ ...input, document: { ...input.document, master: { ...input.document.master, link: e.target.value || null } } })} /></label>
            <details className={styles.evidence}><summary>Post settings & hashtags</summary><div>
            <div className={styles.twoFields}><label>Draft title<input value={input.title} {...fieldIssueProps('title')} onChange={e => edit({ ...input, title: e.target.value })} /></label><label>Content type<input value={input.content_type} {...fieldIssueProps('content_type')} onChange={e => edit({ ...input, content_type: e.target.value })} /></label></div>
            <label>Master hashtags<input value={hashtagText} {...fieldIssueProps('document.master.hashtags')} onChange={e => { setHashtagText(e.target.value); edit({ ...input, document: { ...input.document, master: { ...input.document.master, hashtags: e.target.value.split(/\s+/).filter(Boolean) } } }); }} /><span className={styles.muted}>Separate hashtags with spaces. Prepared captions use the verified facts and the selected account’s limits.</span></label>
            </div></details>
            {post?.origin_type === 'generated' && <GeneratedEvidence key={post.revision_id} postId={post.id} revisionId={post.revision_id} expectedVersion={post.version} />}<details className={styles.evidence}><summary>Source references</summary><div><p className={styles.muted}>Original publisher references support this post. Readers can find them on its AuditGava destination.</p>{input.references.map((reference, index) => <div className={styles.fields} key={index}><label>Source URL {index + 1}<input type='url' value={reference.url} {...fieldIssueProps(`references.${index}.url`)} onChange={e => edit({ ...input, references: input.references.map((r, i) => i === index ? { ...r, url: e.target.value } : r) })} /></label><label>Source label {index + 1}<input value={reference.label ?? ''} {...fieldIssueProps(`references.${index}.label`)} onChange={e => edit({ ...input, references: input.references.map((r, i) => i === index ? { ...r, label: e.target.value } : r) })} /></label>{httpsUrl(reference.url) && <a href={httpsUrl(reference.url)} target='_blank' rel='noopener noreferrer'>Open source {index + 1}</a>}<button type='button' className={styles.button} onClick={() => edit({ ...input, references: input.references.filter((_, i) => i !== index) })}>Remove source {index + 1}</button></div>)}<button type='button' className={styles.button} onClick={() => edit({ ...input, references: [...input.references, { url: '' }] })}>Add source reference</button></div></details>
            {post?.origin_type !== 'generated' && <details className={styles.evidence}><summary>Images & video</summary><div><section tabIndex={-1} {...fieldIssueProps('document.master.media')}><SocialMedia label='Master' contextKey={`${post?.id ?? composerContext}:master`} onBusyChange={active => mediaBusyChanged('master', active)} media={input.document.master.media} onChange={changeMasterMedia} /></section></div></details>}
            <fieldset className={styles.destinations}><legend>Destinations</legend>
              {!accountsAvailable ? <p className={styles.notice}>Connected accounts could not be loaded. Saved selections are preserved; publishing is unavailable until accounts can be verified.</p> : !accounts.length && <p className={styles.empty}>No connected accounts. You can save a manual draft.</p>}
              <div className={styles.accounts}>{accounts.map(a => <label className={styles.account} key={a.id}><input type='checkbox' checked={input.document.targets.some(t => t.account_id === a.id)} onChange={e => select(a.id, e.target.checked)} /><span>{platformLabels[a.platform]} · {a.display_name}<small>{a.handle ?? 'Handle unavailable'} · {a.connection_state}{!a.publishing_enabled ? ' · publishing disabled' : ''}</small></span></label>)}</div>
              {input.document.targets.filter(t => !accounts.some(a => a.id === t.account_id)).map(t => <label key={t.account_id} className={styles.account}><input type='checkbox' checked onChange={() => select(t.account_id, false)} /><span>Unavailable account · {t.account_id}<small>Selection retained. Uncheck to explicitly remove it.</small></span></label>)}
            </fieldset>
          </fieldset>
          <div data-composer-panel='preview' className={`${styles.fields} ${mobilePanel === 'editor' ? styles.mobileHidden : ''}`}>
            <h3>Post preview</h3>
            <div className={styles.tabs} aria-label='Account preview tabs'>{input.document.targets.map((t, index) => { const a = accounts.find(a => a.id === t.account_id); return <button type='button' key={`${t.account_id}-${index}`} aria-pressed={activeAccount === t.account_id} onClick={() => setActiveAccount(t.account_id)}>{a ? `${platformLabels[a.platform]} · ${a.display_name}` : 'Unavailable account'}</button>; })}</div>
            <SocialPreview master={input.document.master} target={target} account={account} validation={valid?.targets.find(t => t.account_id === target?.account_id)} />
            {target && <details className={styles.evidence}><summary>Customize this destination</summary><fieldset tabIndex={-1} {...fieldIssueProps(`document.targets.${input.document.targets.indexOf(target)}`)} disabled={locked} className={`${styles.destinations} ${styles.fields}`}><label>Account format<select {...fieldIssueProps(`document.targets.${input.document.targets.indexOf(target)}.format`)} value={target.format} onChange={e => changeTarget({ ...target, format: e.target.value as DocumentTarget['format'] })}>{(['text', 'image', 'carousel', 'video', 'reel'] as const).map(format => <option key={format} value={format}>{format}{supportedFormats(account).length && !supportedFormats(account).includes(format) ? ' · unsupported' : ''}</option>)}</select></label>{targetHints(input.document.master, target, account).map((hint, index) => <p className={styles.notice} key={index}>{hint}</p>)}<p className={styles.muted}>{Array.from(resolveContent(input.document.master, target).text).length} characters · provisional account count</p>{account?.platform === 'tiktok' && <TikTokControls key={`tiktok:${target.account_id}`} target={target} onChange={changeTarget} />}<SocialOverrides fieldIssueProps={field => fieldIssueProps(`document.targets.${input.document.targets.indexOf(target)}.overrides.${field}.value`)} key={target.account_id} contextKey={post?.id ?? composerContext} master={input.document.master} target={target} onMediaBusyChange={active => mediaBusyChanged(`account:${target.account_id}`, active)} onChange={changeTarget} /></fieldset></details>}
          </div>
        </div>
      </fieldset>
      {valid && <section className={styles.validation} aria-label='Backend validation'><h3>Saved revision validation</h3><p>{allValid ? 'All selected destinations passed.' : 'Publication blocked. Every selected destination must pass.'} · {valid.rules_version}</p>{valid.errors.map((issue, i) => <p className={styles.notice} key={i}>{issue.message}</p>)}{valid.targets.map((t, index) => <div className={styles.validationTarget} key={`${t.account_id}-${index}`}><strong>{t.platform ? platformLabels[t.platform] : 'Unknown platform'} · {accounts.find(a => a.id === t.account_id)?.display_name ?? 'Unavailable account'} · {t.valid ? 'Valid' : 'Needs attention'}</strong><ul>{[...t.errors, ...t.warnings].map((issue, i) => <li key={i}>{issue.message}</li>)}</ul></div>)}{warningCodes.map(code => <label className={styles.reviewCheck} key={code}><input type='checkbox' checked={acknowledged.includes(code)} disabled={commandBusy} onChange={e => setAcknowledged(e.target.checked ? [...acknowledged, code] : acknowledged.filter(c => c !== code))} />Acknowledge {code}: {warnings.filter(w => w.code === code).map(w => w.message).join(' ')}</label>)}</section>}
      {post && effectivePost?.editorial_state !== 'archived' && effectivePost?.publication && effectivePost.publication.approved_by !== null && <SocialScheduleControls post={effectivePost} system={system} disabled={commandBusy || dirty || stale} onUpdated={adopt} />}
      {post && <><div className={styles.actions}><button type='button' className={styles.button} disabled={commandBusy || live.isFetching} onClick={() => live.refetch()}>Refresh revision & results</button></div><SocialResults readOnly={effectivePost?.editorial_state === 'archived'} targets={latestResults} accounts={accounts} postId={post.id} />{effectivePost?.cancellation && <p className={styles.notice}>{effectivePost.cancellation.message} · {effectivePost.cancellation.in_flight_target_ids.length} in-flight destination(s) reported.</p>}</>}
      {!!effectivePost?.historical_target_count && <SocialDeliveryHistory key={effectivePost.id} postId={effectivePost.id} preview={effectivePost.historical_targets} count={effectivePost.historical_target_count} accounts={accounts} />}
    </div>
    <div className={styles.footer}>
      <p className={styles.muted}>{system ? system.publishing_enabled ? 'Publishing enabled. Backend gates are checked again for every command.' : 'Publishing is paused. Draft saving and review remain available.' : 'Publishing status unavailable. Draft saving remains available.'}</p>
      {mediaPending && <p role='status'>A media upload is pending. Text edits remain available; save, validation and publication resume after inspection finishes.</p>}
      {!locked && <><label className={styles.reviewCheck}><input type='checkbox' checked={attested} disabled={commandBusy} onChange={e => setAttested(e.target.checked)} />I checked the facts and sources. This attestation is required when the server identifies sensitive content.</label><div className={styles.actions}><button type='button' className={`${styles.button} ${!dirty && !allValid ? styles.primary : ''}`} disabled={commandBusy || stale} onClick={validate}>Save & validate</button><button type='button' className={`${styles.button} ${!dirty && allValid ? styles.primary : ''}`} disabled={!canSubmit} onClick={() => editorial('submit')}>Submit for review</button></div>
        {!allValid && <p className={styles.muted}>The saved revision must pass every selected account’s checks before publication.</p>}
        {post?.editorial_state === 'pending_review' && <button type='button' className={`${styles.button} ${!dirty && allValid ? styles.primary : ''}`} disabled={commandBusy || !allValid} onClick={() => editorial('approve')}>Approve revision</button>}
        <details className={styles.evidence}><summary>Delivery & scheduling</summary><div><p className={styles.muted}>Publishing is a separate action after review. The current system and account gates must permit delivery.</p><button type='button' className={styles.button} disabled={!canPublish} onClick={() => publish(false)}>Publish now</button></div>
        <div className={styles.actions}><button type='button' className={styles.button} disabled={commandBusy || (!!currentPublication && !readyAuthorization)} aria-expanded={scheduleOpen} onClick={() => setScheduleOpen(!scheduleOpen)}>Schedule</button></div>
        {scheduleOpen && <div className={styles.schedule}><h3>One schedule for all selected accounts</h3><div className={styles.twoFields}><label>Local publish time<input type='datetime-local' value={localTime} disabled={commandBusy} onChange={e => { setLocalTime(e.target.value); setOffsetChoice(''); }} /></label><label>IANA timezone<input value={timezone} disabled={commandBusy} onChange={e => { setTimezone(e.target.value); setOffsetChoice(''); }} /></label></div>{civil.error && <p className={styles.notice} role='alert'>{civil.error}</p>}{civil.candidates.length > 1 && <label>UTC offset (this local time occurs twice)<select value={offsetChoice} disabled={commandBusy} onChange={e => setOffsetChoice(e.target.value)}><option value=''>Choose the intended occurrence</option>{civil.candidates.map(c => <option key={c.offset} value={c.offset}>{c.offset} · {c.utc}</option>)}</select></label>}{selectedTime && <p>UTC preview: {selectedTime.utc} · offset {selectedTime.offset}</p>}<button type='button' className={`${styles.button} ${styles.primary}`} disabled={!canPublish || !selectedTime || Date.parse(selectedTime.utc) <= Date.now()} onClick={() => publish(true)}>Confirm schedule</button><p className={styles.muted}>The server rejects invalid, ambiguous or past times. A scheduled target still requires publishing gates to be enabled when due.</p></div>}
        </details>
        {post?.editorial_state === 'pending_review' && <details className={styles.evidence}><summary>Return draft with a reason</summary><div className={styles.fields}><label>Reason to reject<input value={rejectReason} disabled={commandBusy} onChange={e => setRejectReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={commandBusy || stale || dirty || !rejectReason.trim()} onClick={() => editorial('reject')}>Reject draft</button></div></details>}
        {cancelledAuthorization && <div className={styles.fields}><label>Reason to resume<input value={resumeReason} disabled={commandBusy} onChange={e => setResumeReason(e.target.value)} /></label><button type='button' className={styles.button} disabled={!canResume} onClick={resume}>Resume unsent deliveries</button><p className={styles.muted}>The server checks that every destination is unchanged, unsent and within its original deadlines. Future schedules are kept; expired or attempted deliveries require a new draft.</p></div>}
      </>}
      <details className={styles.evidence} open={effectivePost?.editorial_state === 'archived'}><summary>More draft actions</summary><div>
      {post && effectivePost && <SocialArchiveControls onBusyChange={archiveBusyChanged} post={effectivePost} disabled={commandBusy || dirty || stale} onUpdated={adopt} />}
      {post && <div className={styles.actions}>{currentPublication && effectivePost?.editorial_state !== 'archived' && <button type='button' className={styles.button} disabled={commandBusy || stale || dirty} onClick={() => editorial('cancel')}>Cancel unsent deliveries</button>}<button type='button' className={styles.button} disabled={commandBusy || dirty || stale} onClick={() => editorial('duplicate')}>Duplicate as new manual draft</button></div>}
      </div></details>
    </div>
    {isMobile ? createPortal(<div className={styles.workspace} data-social-actions-portal>{primaryActions}</div>, document.body) : primaryActions}
  </article>;
}
