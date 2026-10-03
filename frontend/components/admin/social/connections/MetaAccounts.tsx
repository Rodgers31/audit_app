'use client';
import { connectionApi, ConnectionError, MetaDiscoveredFlow } from '@/lib/api/socialConnections';
import type { SocialAccount } from '@/lib/api/social';
import { useSocialAccounts } from '@/lib/hooks/useSocial';
import { useMetaAccountHealth, useMetaConnectionStatus } from '@/lib/hooks/useSocialConnections';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { receiveMetaCallback } from './callbackSecurity';
import styles from '../social.module.css';

function ErrorNotice({ error }: { error: unknown }) {
  if (!error) return null;
  return <div className={`${styles.notice} ${styles.error}`} role='alert'>{error instanceof ConnectionError ? <><p>{error.message}</p><p className={styles.muted}>{error.code}{error.requestId ? ` · Request ${error.requestId}` : ''}</p></> : <p>Account status is unavailable. Refresh before continuing.</p>}</div>;
}
function AccountCard({ account, onReconnect, refresh, connectAvailable }: { account: SocialAccount; connectAvailable: boolean; onReconnect: (id: string) => void; refresh: () => void }) {
  const [expanded, setExpanded] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
  const health = useMetaAccountHealth(account.id, expanded);
  const disconnectKey = useRef<{ credential: string; version: number; key: string } | undefined>(undefined);
  async function disconnect() {
    if (!health.data || busy) return;
    setBusy(true); setError(undefined);
    const version = health.data.credential_version, credential = health.data.credential_id;
    if (disconnectKey.current?.version !== version || disconnectKey.current?.credential !== credential) disconnectKey.current = { credential, version, key: crypto.randomUUID() };
    try { await connectionApi.disconnect(account.id, credential, version, disconnectKey.current.key); await health.refetch(); refresh(); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  return <article className={styles.accountCard}>
    <h3>{account.platform === 'facebook' ? 'Facebook Page' : 'Instagram'} · {account.display_name}</h3>
    <p>{account.handle ? `@${account.handle}` : 'Page identity'} · {health.data?.connection_state ?? account.connection_state}</p>
    <p className={styles.muted}>Publishing {account.publishing_enabled ? 'enabled by account controls' : 'disabled'}. Publishing adapter unavailable.</p>
    <div className={styles.actions}><button className={styles.button} type='button' aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>Connection details</button><button className={styles.button} type='button' disabled={busy || !connectAvailable} onClick={() => onReconnect(account.id)}>Reconnect identity</button></div>
    {expanded && <div className={styles.fields}>
      {health.isPending && <p role='status'>Loading connection health…</p>}
      <ErrorNotice error={health.error ?? error} />
      {health.data && <><p>Account ID: {health.data.external_account_id}</p><p>Method: Facebook Login · {health.data.api_product}</p><p>Granted permissions: {health.data.granted_scopes.join(', ') || 'none'}</p><p>Missing permissions: {health.data.missing_scopes.join(', ') || 'none reported'}</p><p>Grant expiry: {health.data.access_expires_at ? new Date(health.data.access_expires_at).toLocaleString() : 'No timed expiry reported; authorization remains revocable'}</p><p>Data access expiry: {health.data.data_access_expires_at ? new Date(health.data.data_access_expires_at).toLocaleString() : 'Not reported'}</p><p>Parent user grant expiry: {health.data.parent_access_expires_at ? new Date(health.data.parent_access_expires_at).toLocaleString() : 'Not reported'}. {health.data.parent_grant_reconnect_required ? 'Reconnect the parent grant for future discovery.' : 'Parent grant does not determine a timed Page-token expiry.'}</p><p className={styles.muted}>Last successful API read: {health.data.last_api_success_at ? new Date(health.data.last_api_success_at).toLocaleString() : 'Unavailable'}. Renewal requires Facebook Login reconnection.</p><p>Disconnect disables both destinations sharing this Page grant. Provider permission removal must be confirmed separately.</p><button className={styles.button} type='button' disabled={busy || health.data.connection_state === 'disconnected'} onClick={disconnect}>{busy ? 'Disabling connection…' : 'Disable local connection'}</button></>}
      <button className={styles.button} type='button' disabled={health.isFetching} onClick={() => health.refetch()}>Refresh connection health</button>
    </div>}
  </article>;
}

export default function MetaAccounts() {
  const accounts = useSocialAccounts(), status = useMetaConnectionStatus(), { user } = useAuth();
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(), [discovery, setDiscovery] = useState<MetaDiscoveredFlow>();
  const [page, setPage] = useState(''), [includeInstagram, setIncludeInstagram] = useState(false);
  const [confirmed, setConfirmed] = useState(false), [expired, setExpired] = useState(false);
  const pending = useRef<{ popup: Window; state: string; redirect: string; key: string } | null>(null);
  const selectionKey = useRef<{ signature: string; key: string } | null>(null);
  const selected = discovery?.choices.find(c => c.page_id === page);
  useEffect(() => {
    const handler = async (event: MessageEvent) => {
      const flow = pending.current;
      const payload = receiveMetaCallback(event, window.location.origin, flow?.popup ?? null, flow?.state ?? null);
      if (!flow || !payload) return;
      pending.current = null; flow.popup.close(); setBusy(true);
      if (payload.denied || !payload.code) { setError(new ConnectionError('OAUTH_DENIED', 'Meta authorization was declined. Start a new connection when ready.')); setBusy(false); return; }
      try { const result = await connectionApi.complete(payload.code, flow.state, flow.redirect, flow.key); setDiscovery(result); setPage(''); setIncludeInstagram(false); }
      catch (e) { setError(e); }
      finally { setBusy(false); }
    };
    window.addEventListener('message', handler);
    return () => { window.removeEventListener('message', handler); pending.current?.popup.close(); pending.current = null; };
  }, [user?.id]);
  useEffect(() => {
    setDiscovery(undefined); setPage(''); setConfirmed(false); setError(undefined); setBusy(false);
  }, [user?.id]);
  useEffect(() => {
    if (!discovery) { setExpired(false); return; }
    const remaining = Date.parse(discovery.expires_at) - Date.now();
    setExpired(remaining <= 0);
    const timer = window.setTimeout(() => setExpired(true), Math.max(0, remaining));
    return () => window.clearTimeout(timer);
  }, [discovery]);
  async function start(reconnect?: string) {
    if (busy || !status.data?.available) return;
    pending.current?.popup.close(); pending.current = null;
    const popup = window.open('about:blank', 'AuditGavaMetaConnection', 'popup,width=700,height=760');
    if (!popup) { setError(new ConnectionError('POPUP_BLOCKED', 'Allow the connection popup and try again.')); return; }
    setBusy(true); setError(undefined); setDiscovery(undefined); setConfirmed(false);
    const redirect = window.location.origin + '/admin/social/accounts/callback';
    try {
      const flow = await connectionApi.start(redirect, reconnect);
      const url = new URL(flow.authorize_url);
      if (url.searchParams.get('redirect_uri') !== redirect || Date.parse(flow.expires_at) <= Date.now()) throw new ConnectionError('INVALID_RESPONSE', 'The connection callback or expiry differs from this admin page.');
      pending.current = { popup, state: url.searchParams.get('state')!, redirect, key: crypto.randomUUID() };
      popup.location.replace(flow.authorize_url);
    } catch (e) { popup.close(); setError(e); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!discovery || !selected || busy || expired) return;
    const instagram = includeInstagram ? selected.instagram_id : null;
    const signature = JSON.stringify([discovery.flow_id, page, instagram]);
    if (selectionKey.current?.signature !== signature) selectionKey.current = { signature, key: crypto.randomUUID() };
    setBusy(true); setError(undefined);
    try { await connectionApi.select(discovery.flow_id, page, instagram, selectionKey.current.key); setDiscovery(undefined); setConfirmed(true); await accounts.refetch(); }
    catch (e) { setError(e); }
    finally { setBusy(false); }
  }
  return <div className={styles.workspace}>
    <div className={styles.toolbar}><Link href='/admin/social'>Back to social publishing</Link><button className={styles.button} type='button' disabled={busy} onClick={() => { void accounts.refetch(); void status.refetch(); }}>Refresh accounts</button></div>
    <div className={styles.status}><strong>Manual account connection</strong><span>New connections keep publishing disabled.</span></div>
    <ErrorNotice error={error ?? accounts.error ?? status.error} />
    {status.isPending && <p role='status'>Checking Meta connection availability…</p>}
    {status.data && <div className={styles.accountCard}><h2>Facebook and Instagram</h2><p>Connect the AuditGava Facebook Page and explicitly choose its linked professional Instagram account.</p>{!status.data.available && <div className={styles.notice}><p>Meta connections are unavailable until registered app configuration and server credentials are validated.</p><p className={styles.muted}>{status.data.blockers.join(' · ')}</p></div>}<p className={styles.muted}>Access: {status.data.access_mode.replaceAll('_', ' ')}. Requested permissions: {status.data.scopes.join(', ')}. Threads requires a separate future connection.</p><button className={`${styles.button} ${styles.primary}`} type='button' disabled={busy || !status.data.available} onClick={() => start()}>{busy ? 'Connecting…' : 'Connect owned Meta accounts'}</button>{pending.current && <p role='status'>Complete authorization in the Meta popup. The same administrator session must confirm the accounts.</p>}</div>}
    {discovery && <section className={styles.accountCard} aria-label='Choose exact Meta identities'><h2>Confirm account identities</h2><p>Granted permissions: {discovery.granted_scopes.join(', ')}</p>{discovery.choices.length === 0 && <p>No connectable Pages were returned. Review the Meta grant and Page content access, then reconnect.</p>}<label>Facebook Page<select value={page} disabled={busy || expired} onChange={e => { setPage(e.target.value); setIncludeInstagram(false); }}><option value=''>Choose an exact Page</option>{discovery.choices.map(c => <option key={c.page_id} value={c.page_id} disabled={!c.page_eligible}>{c.display_name} · {c.page_id}{!c.page_eligible ? ' · insufficient permissions or content tasks' : ''}</option>)}</select></label>{selected && <><p>Page tasks: {selected.tasks.join(', ') || 'none reported'}</p>{selected.instagram_id ? <label className={styles.reviewCheck}><input type='checkbox' checked={includeInstagram} disabled={busy || expired || !selected.instagram_eligible} onChange={e => setIncludeInstagram(e.target.checked)} /><span>Also connect {selected.instagram_name} · @{selected.instagram_handle} · {selected.instagram_id}{!selected.instagram_eligible && <small> · professional eligibility, content tasks or permissions missing: {selected.missing_instagram_scopes.join(', ') || 'eligibility unverified'}</small>}</span></label> : <p>No accessible professional Instagram identity is linked to this Page.</p>}</>}{expired && <p role='alert'>This selection flow expired. Start a new connection.</p>}<button className={`${styles.button} ${styles.primary}`} type='button' disabled={busy || expired || !selected?.page_eligible} onClick={confirm}>Confirm selected identities</button></section>}
    {confirmed && <p className={styles.success} role='status'>Selected accounts connected. Publishing remains disabled.</p>}
    <section className={styles.accountList} aria-label='Connected Meta accounts'><h2>Connected identities</h2>{accounts.isPending && <p role='status'>Loading actual accounts…</p>}{accounts.data?.filter(a => ['facebook','instagram'].includes(a.platform)).length === 0 && <p className={styles.empty}>No Meta accounts are connected. Save manual drafts while account configuration is unavailable.</p>}{accounts.data?.filter(a => ['facebook','instagram'].includes(a.platform)).map(account => <AccountCard key={account.id} account={account} connectAvailable={!!status.data?.available && !busy} onReconnect={id => start(id)} refresh={() => accounts.refetch()} />)}</section>
  </div>;
}
