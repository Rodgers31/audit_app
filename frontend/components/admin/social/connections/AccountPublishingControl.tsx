'use client';

import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth/AuthProvider';
import { AccountPublishingStatus, decodeAccountPublishing, sendSocialCommand, socialApi } from '@/lib/api/social';
import { connectionApi } from '@/lib/api/socialConnections';
import styles from '../social.module.css';

const explanations: Record<string, string> = {
  ACCOUNT_DISCONNECTED: 'Connect this account before enabling publishing.',
  NATIVE_ADMISSION_UNAVAILABLE: 'Refresh verified publishing permissions for this account. Reconnect only if its saved grant cannot be verified.',
  CREDENTIAL_UNAVAILABLE: 'The saved credential is missing, expired, revoked or awaiting renewal reconciliation.',
  PRIVACY_GRANT_BLOCKED: 'A retained privacy request blocks this saved grant. Keep publishing paused until its ownership is resolved.',
  PRIVACY_STATE_UNAVAILABLE: 'Privacy-request ownership for this grant could not be verified. Keep publishing paused until it is resolved.',
  ACCOUNT_HELD: 'An account safety hold needs reconciliation.',
  DELIVERY_UNRESOLVED: 'A retained delivery operation needs reconciliation before publishing can be enabled.',
  GLOBAL_PUBLISHING_DISABLED: 'Global publishing is off. Enabling this account will not change it.',
  PLATFORM_CONTROLS_UNAVAILABLE: 'Platform publishing controls are unreadable. An administrator must repair them before enabling publishing.',
  PLATFORM_PUBLISHING_DISABLED: 'Publishing for this platform is paused globally.',
  NATIVE_RUNTIME_UNAVAILABLE: 'The native runtime is unavailable. Delivery remains blocked.',
};

/** Explicit local account consent; no optimistic success or automatic retry. */
export default function AccountPublishingControl({ accountId, name, refresh, canVerifyMeta = false }: { accountId: string; name: string; refresh: () => void; canVerifyMeta?: boolean }) {
  const { user } = useAuth();
  const scope = `${user?.id}:${accountId}`;
  const generation = useRef({ scope, epoch: 0, mounted: true });
  if (generation.current.scope !== scope) generation.current = { scope, epoch: generation.current.epoch + 1, mounted: true };
  const [status, setStatus] = useState<AccountPublishingStatus>();
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [message, setMessage] = useState<string>();
  const inFlight = useRef(false);
  const [error, setError] = useState<string>();
  const pending = useRef<{ signature: string; key: string } | undefined>(undefined);
  const capture = () => {
    const epoch = generation.current.epoch;
    return () => generation.current.mounted && generation.current.epoch === epoch && generation.current.scope === scope;
  };
  useEffect(() => {
    generation.current.mounted = true;
    setStatus(undefined); setExpanded(false); setBusy(false); setVerifying(false); setMessage(undefined); setError(undefined); pending.current = undefined; inFlight.current = false;
    return () => { generation.current.mounted = false; generation.current.epoch += 1; };
  }, [scope]);
  async function load() {
    if (busy || inFlight.current || !user?.id) return;
    inFlight.current = true;
    const current = capture(); setBusy(true); setError(undefined); setMessage(undefined); setExpanded(true);
    try { const value = await socialApi.accountPublishing(accountId); if (current()) setStatus(value); }
    catch (e) { if (current()) { setStatus(undefined); setError(e instanceof Error ? e.message : 'Account publishing readiness is unavailable.'); } }
    finally { if (current()) { inFlight.current = false; setBusy(false); } }
  }
  async function change(enabled: boolean) {
    if (!status || busy || inFlight.current || !user?.id || (enabled && !status.enable_available)) return;
    inFlight.current = true;
    const current = capture(); setBusy(true); setError(undefined); setMessage(undefined);
    const body = { expected_controls_version: status.controls_version, expected_state: status.state_token, publishing_enabled: enabled, reason: enabled ? 'Administrator enabled this account for manual publishing.' : 'Administrator paused publishing for this account.' };
    const signature = JSON.stringify([scope, 'consent', body]);
    if (pending.current?.signature !== signature) pending.current = { signature, key: crypto.randomUUID() };
    try {
      const value = await sendSocialCommand(`/accounts/${encodeURIComponent(accountId)}/publishing`, body, pending.current.key, v => {
        const decoded = decodeAccountPublishing(v);
        if (decoded.account_id !== accountId || decoded.publishing_enabled !== enabled
            || decoded.controls_version !== body.expected_controls_version + 1 || decoded.state_token === body.expected_state) throw new Error('Account publishing response does not match this request. Refresh before continuing.');
        return decoded;
      }, 'patch');
      if (!current()) return;
      setStatus(value); pending.current = undefined; refresh();
    } catch (e) { if (current()) setError(e instanceof Error ? e.message : 'Account publishing change was not confirmed. Retry the same action or refresh.'); }
    finally { if (current()) { inFlight.current = false; setBusy(false); } }
  }
  async function verify() {
    if (!canVerifyMeta || !status || status.publishing_enabled || busy || inFlight.current || !user?.id) return;
    inFlight.current = true;
    const current = capture(); setBusy(true); setVerifying(true); setError(undefined); setMessage(undefined);
    const body = { expected_controls_version: status.controls_version, expected_state: status.state_token, reason: 'Administrator requested verification of this saved Meta grant for publishing.' };
    const signature = JSON.stringify([scope, 'verify', body]);
    if (pending.current?.signature !== signature) pending.current = { signature, key: crypto.randomUUID() };
    try {
      const value = await connectionApi.verifyPublishingAccess(accountId, body, pending.current.key);
      if (!current()) return;
      setStatus(value); pending.current = undefined; setMessage('Publishing access verified. Account publishing is still paused.'); refresh();
    } catch (e) { if (current()) setError(e instanceof Error ? e.message : 'Publishing access was not confirmed. Retry the same verification or refresh.'); }
    finally { if (current()) { inFlight.current = false; setBusy(false); setVerifying(false); } }
  }
  return <div className={styles.fields} aria-label={`Publishing controls for ${name}`}>
    <button type='button' className={styles.button} disabled={busy || !user?.id} aria-expanded={expanded} onClick={load}>{busy ? 'Checking account publishing…' : 'Refresh account publishing controls'}</button>
    {error && <p role='alert'>{error}</p>}
    {message && <p role='status'>{message}</p>}
    {expanded && status && <>
      <p>Account publishing is {status.publishing_enabled ? 'enabled' : 'paused'}. This setting permits manually approved posts for this account; global controls and delivery readiness still apply.</p>
      {Array.from(new Set([...status.enable_blockers, ...status.delivery_holds])).map(code => <p key={code}>{explanations[code] ?? `Publishing readiness requires attention (${code}).`}</p>)}
      <p className={styles.muted}>Delivery also requires a current worker heartbeat. Pausing preserves any in-flight or uncertain operation; it does not recall a post already sent.</p>
      {canVerifyMeta && <div>
        <p>Verify the saved Meta grant against the exact connected identity and current publishing permissions. Verification leaves account publishing paused and does not post anything.</p>
        <button type='button' className={styles.button} disabled={busy || status.publishing_enabled} onClick={verify}>{verifying ? 'Verifying publishing access…' : `Verify existing publishing access for ${name}`}</button>
        {status.publishing_enabled && <p>Pause this account before verifying its saved grant.</p>}
      </div>}
      <button type='button' className={styles.button} disabled={busy || (!status.publishing_enabled && !status.enable_available)} onClick={() => change(!status.publishing_enabled)}>{busy ? 'Saving account publishing…' : status.publishing_enabled ? `Pause publishing for ${name}` : `Enable publishing for ${name}`}</button>
    </>}
  </div>;
}
