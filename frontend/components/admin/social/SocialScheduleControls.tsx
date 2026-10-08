'use client';
import { decodePost, ScheduleEditInput, SocialApiError, SocialPost, SocialSystemStatus } from '@/lib/api/social';
import { useSocialMutation } from '@/lib/hooks/useSocial';
import { useMemo, useRef, useState } from 'react';
import { SocialErrorBanner } from './SocialNotice';
import { resolveCivilTime } from './socialDocument';
import styles from './social.module.css';

export default function SocialScheduleControls({ post, system, disabled, onUpdated }: { post: SocialPost; system?: SocialSystemStatus; disabled: boolean; onUpdated: (post: SocialPost) => void }) {
  const publication = post.publication!;
  const mutation = useSocialMutation();
  const [reason, setReason] = useState('');
  const [localTime, setLocalTime] = useState(publication.requested_local_time?.slice(0, 16) ?? '');
  const [timezone, setTimezone] = useState(publication.schedule_timezone ?? 'Africa/Nairobi');
  const [offsetChoice, setOffsetChoice] = useState('');
  const [acknowledged, setAcknowledged] = useState<string[]>([]);
  const [message, setMessage] = useState('');
  const running = useRef(false);
  const civil = useMemo(() => resolveCivilTime(localTime, timezone), [localTime, timezone]);
  const selected = civil.candidates.length === 1 ? civil.candidates[0] : civil.candidates.find(c => c.offset === offsetChoice);
  const blocked = disabled || mutation.isPending || post.editorial_state !== 'approved' || !!publication.cancel_requested_at || system?.publishing_enabled !== true || !reason.trim() || !post.targets.some(t => ['ready', 'queued'].includes(t.state)) || post.targets.some(t => ['claimed', 'dispatching', 'processing', 'reconciling'].includes(t.state));
  const warnings = mutation.error?.code === 'WARNINGS_NOT_ACKNOWLEDGED' ? mutation.error.fieldErrors : [];
  async function change(scheduled: boolean) {
    if (blocked || running.current || scheduled && !selected) return;
    running.current = true; setMessage('');
    const requestedAt = Date.now(), requestedLocal = localTime.length === 16 ? `${localTime}:00` : localTime;
    const body: ScheduleEditInput = { expected_version: post.version, publication_id: publication.id, expected_publication_version: publication.version, reason, acknowledged_warning_codes: acknowledged };
    const request = scheduled ? { ...body, schedule: { local_time: requestedLocal, timezone, utc_offset: selected!.offset } } : body;
    try {
      const result = await mutation.run(`/posts/${encodeURIComponent(post.id)}/${scheduled ? 'reschedule' : 'publish-now'}`, request, value => {
        const next = decodePost(value), changed = next.publication;
        const due = Date.parse(changed?.scheduled_for ?? '');
        const stable = next.id === post.id && next.version === post.version + 1 && next.revision_id === post.revision_id && next.editorial_state === post.editorial_state && JSON.stringify(next.document) === JSON.stringify(post.document) && JSON.stringify(next.references) === JSON.stringify(post.references) && changed && changed.id === publication.id && changed.revision_id === publication.revision_id && changed.version === publication.version + 1 && changed.approved_at === publication.approved_at && changed.approved_by === publication.approved_by && changed.cancel_requested_at === publication.cancel_requested_at;
        const exactTime = Number.isFinite(due) && (scheduled ? due === Date.parse(selected!.utc) && changed?.schedule_timezone === timezone && changed?.requested_local_time === requestedLocal : due >= requestedAt - 5_000 && due <= Date.now() + 5_000 && changed?.schedule_timezone === 'UTC');
        let moved = 0;
        const stableTargets = next.targets.length === post.targets.length && new Set(next.targets.map(t => t.id)).size === post.targets.length && post.targets.every(old => {
          const target = next.targets.find(t => t.id === old.id);
          if (!target || target.account_id !== old.account_id || target.platform !== old.platform) return false;
          if (JSON.stringify(target) === JSON.stringify(old)) return true;
          if (!['ready', 'queued'].includes(old.state) || old.published_at !== null || old.remote_url !== null || target.state !== 'queued' || target.published_at !== old.published_at || target.remote_url !== old.remote_url || target.safe_error_message !== old.safe_error_message || Date.parse(target.next_action_at ?? '') !== due) return false;
          moved++; return true;
        });
        if (!stable || !exactTime || !stableTargets || (moved === 0 && !post.targets.some(t => ['ready', 'queued'].includes(t.state) && Date.parse(t.next_action_at ?? '') === due))) throw new SocialApiError('INVALID_RESPONSE', 'The schedule response did not confirm the unchanged authorization, exact due time and independent destinations. Refresh before continuing; the original command key was preserved.');
        return next;
      }, { postId: post.id });
      onUpdated(result); setAcknowledged([]);
      setMessage(scheduled ? 'Schedule updated for unchanged unsent destinations. Each delivery remains independently tracked.' : 'Publish-now accepted for unchanged unsent destinations. The worker confirms each delivery separately.');
    } catch { /* The typed error and exact command key remain available. */ }
    finally { running.current = false; }
  }
  return <section className={styles.schedule} aria-label='Schedule management'>
    <h3>Manage unchanged deliveries</h3>
    <p>{publication.requested_local_time ?? 'Local time unavailable'} · {publication.schedule_timezone ?? 'Timezone unavailable'}{publication.scheduled_for ? ` · ${publication.scheduled_for} (UTC)` : ' · Dispatch has not been requested'}</p>
    <p className={styles.muted}>Reviewed by {publication.approved_by} at {publication.approved_at}. Only untouched unsent destinations can move. A worker claim blocks schedule changes; accepted remote requests may still complete after cancellation.</p>
    {publication.cancel_requested_at && <p className={styles.notice}>Cancellation requested at {publication.cancel_requested_at} (UTC). Worker-owned or attempted destinations remain visible until acknowledged.</p>}
    <label>Reason for schedule change<input value={reason} disabled={disabled || mutation.isPending} onChange={e => setReason(e.target.value)} /></label>
    <div className={styles.twoFields}><label>New local publish time<input type='datetime-local' value={localTime} disabled={disabled || mutation.isPending} onChange={e => { setLocalTime(e.target.value); setOffsetChoice(''); }} /></label><label>Schedule timezone<input value={timezone} disabled={disabled || mutation.isPending} onChange={e => { setTimezone(e.target.value); setOffsetChoice(''); }} /></label></div>
    {civil.error && <p className={styles.notice}>{civil.error}</p>}
    {civil.candidates.length > 1 && <label>New UTC offset<select value={offsetChoice} onChange={e => setOffsetChoice(e.target.value)}><option value=''>Choose the intended occurrence</option>{civil.candidates.map(c => <option key={c.offset} value={c.offset}>{c.offset} · {c.utc}</option>)}</select></label>}
    {selected && <p className={styles.muted}>New UTC due time: {selected.utc}</p>}
    {warnings.map(w => <label key={`${w.code}:${w.field}`} className={styles.reviewCheck}><input type='checkbox' checked={acknowledged.includes(w.code)} onChange={e => setAcknowledged(e.target.checked ? [...acknowledged, w.code] : acknowledged.filter(c => c !== w.code))} />{w.message}</label>)}
    <div className={styles.actions}><button type='button' className={styles.button} disabled={blocked || !selected || Date.parse(selected.utc) <= Date.now()} onClick={() => change(true)}>Confirm reschedule</button><button type='button' className={styles.button} disabled={blocked} onClick={() => change(false)}>Publish unsent now</button></div>
    {mutation.error && <SocialErrorBanner error={mutation.error} context='schedule' />}
    {message && <p role='status' className={styles.success}>{message}</p>}
  </section>;
}
