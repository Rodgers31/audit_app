'use client';

import {
  getAlerts,
  markAlertRead,
  markAllAlertsRead,
  updateProfile,
  type DataAlert,
} from '@/lib/api/auth';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useWatchlist } from '@/lib/auth/WatchlistProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import { ACCOUNT_MESSAGES as copy } from '@/lib/i18n/messages/account';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';
import AccountDataActions from './AccountDataActions';

const fieldClass = 'mt-1 min-h-11 w-full rounded border border-neutral-text bg-surface-elevated px-3 text-base';
const sectionClass = 'space-y-2 py-4 sm:space-y-3 sm:py-5';
const headingClass = 'font-display text-audit-heading font-semibold';

type Message = { type: 'success' | 'error'; text: string };

function Feedback({ message }: { message: Message | null }) {
  return (
    <p role={message?.type === 'error' ? 'alert' : 'status'}
      className={message?.type === 'error' ? 'text-sm text-signal-alarm' : 'text-sm text-neutral-muted'}>
      {message?.text}
    </p>
  );
}

export default function AccountDashboard({ accountId }: { accountId: string }) {
  const { lang } = useLang();
  const { user, authUser, refreshUser, resetPassword, changeEmail } = useAuth();
  const { items, isLoading: watchlistLoading, remove: removeWatch } = useWatchlist();
  const watchlist = items.filter(item => item.user_id === accountId);
  const legacyTab = useSearchParams().get('tab');
  const watchHeading = useRef<HTMLHeadingElement>(null);
  const alertsHeading = useRef<HTMLHeadingElement>(null);
  const email = authUser?.email ?? '';
  const separator = email.lastIndexOf('@');
  const maskedEmail = separator > 0 ? `${email[0]}•••${email.slice(separator)}` : '';
  const [editedName, setEditedName] = useState<string | null>(null);
  const displayName = editedName ?? user?.display_name ?? '';

  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<Message | null>(null);
  const [newEmail, setNewEmail] = useState('');
  const [emailSending, setEmailSending] = useState(false);
  const [emailMessage, setEmailMessage] = useState<Message | null>(null);
  const [resetSending, setResetSending] = useState(false);
  const [resetMessage, setResetMessage] = useState<Message | null>(null);
  const [watchRemoval, setWatchRemoval] = useState<number | null>(null);
  const [watchError, setWatchError] = useState(false);
  const [alerts, setAlerts] = useState<DataAlert[] | null>(null);
  const [alertsLoadError, setAlertsLoadError] = useState(false);
  const [alertsSaveError, setAlertsSaveError] = useState(false);
  const [marking, setMarking] = useState<number | 'all' | null>(null);

  useEffect(() => {
    const target = legacyTab === 'watchlist' ? watchHeading.current
      : legacyTab === 'alerts' ? alertsHeading.current : null;
    if (!target) return;
    const frame = requestAnimationFrame(() => {
      target.scrollIntoView({ block: 'start' });
      target.focus({ preventScroll: true });
    });
    return () => cancelAnimationFrame(frame);
  }, [legacyTab]);

  const readAlerts = useCallback(async (signal?: AbortSignal) => {
    setAlertsLoadError(false);
    try {
      const result = await getAlerts();
      if (!signal?.aborted) setAlerts(result.filter(alert => alert.user_id === accountId));
    } catch {
      if (!signal?.aborted) setAlertsLoadError(true);
    }
  }, [accountId]);

  useEffect(() => {
    const request = new AbortController();
    void readAlerts(request.signal);
    return () => request.abort();
  }, [readAlerts]);

  async function saveProfile() {
    setSaving(true);
    setSaveMessage(null);
    try {
      await updateProfile(displayName);
      await refreshUser();
      setSaveMessage({ type: 'success', text: copy.saved[lang] });
    } catch {
      setSaveMessage({ type: 'error', text: copy.saveError[lang] });
    } finally {
      setSaving(false);
    }
  }

  async function sendEmailChange() {
    if (!newEmail || newEmail === email) return;
    setEmailSending(true);
    setEmailMessage(null);
    try {
      await changeEmail(newEmail);
      setEmailMessage({ type: 'success', text: copy.emailSent[lang].replace('{email}', newEmail) });
      setNewEmail('');
    } catch {
      setEmailMessage({ type: 'error', text: copy.emailError[lang] });
    } finally {
      setEmailSending(false);
    }
  }

  async function sendReset() {
    if (!email) return;
    setResetSending(true);
    setResetMessage(null);
    try {
      await resetPassword(email);
      setResetMessage({ type: 'success', text: copy.resetSent[lang] });
    } catch {
      setResetMessage({ type: 'error', text: copy.resetError[lang] });
    } finally {
      setResetSending(false);
    }
  }

  async function removeItem(id: number) {
    setWatchRemoval(id);
    setWatchError(false);
    try {
      await removeWatch(id);
    } catch {
      setWatchError(true);
    } finally {
      setWatchRemoval(null);
    }
  }

  async function markRead(target: number | 'all') {
    setMarking(target);
    setAlertsSaveError(false);
    try {
      if (target === 'all') await markAllAlertsRead();
      else await markAlertRead(target);
      setAlerts(current => current?.map(alert =>
        target === 'all' || alert.id === target ? { ...alert, read: true } : alert) ?? null);
    } catch {
      setAlertsSaveError(true);
    } finally {
      setMarking(null);
    }
  }

  return (
    <div className='max-w-3xl divide-y divide-neutral-border text-neutral-text'>
      <section className={`${sectionClass} pt-0 sm:pt-0`} aria-labelledby='account-details'>
        <h2 id='account-details' className={headingClass}>{copy.details[lang]}</h2>
        <form className='space-y-3' onSubmit={event => {
          event.preventDefault();
          void saveProfile();
        }}>
          <label className='block text-sm font-semibold'>
            {copy.name[lang]}
            <input className={fieldClass} type='text' value={displayName} autoComplete='name'
              onChange={event => { setEditedName(event.target.value); setSaveMessage(null); }} disabled={saving} />
          </label>
          <label className='block text-sm font-semibold'>
            {copy.email[lang]}
            <input className={fieldClass} type='text' value={maskedEmail} readOnly />
          </label>
          <div className='flex flex-wrap items-center gap-x-3 gap-y-1'>
            <button type='submit' className='audit-control bg-surface-elevated' disabled={saving}>
              {saving ? copy.saving[lang] : copy.save[lang]}
            </button>
            <Feedback message={saveMessage} />
          </div>
        </form>

        <details className='border-t border-neutral-border pt-2'>
          <summary className='min-h-11 cursor-pointer py-3 text-sm font-semibold'>
            {copy.signInDetails[lang]}
          </summary>
          <div className='space-y-3 pb-1'>
            <form className='space-y-2' onSubmit={event => {
              event.preventDefault();
              void sendEmailChange();
            }}>
              <label className='block text-sm font-semibold'>
                {copy.newEmail[lang]}
                <input className={fieldClass} type='email' autoComplete='email' value={newEmail}
                  onChange={event => setNewEmail(event.target.value)} disabled={emailSending} required />
              </label>
              <button type='submit' className='audit-control'
                disabled={emailSending || !newEmail || newEmail === email}>{copy.emailLink[lang]}</button>
              <Feedback message={emailMessage} />
            </form>
            <div className='border-t border-neutral-border pt-3'>
              <button type='button' className='audit-control' onClick={sendReset}
                disabled={!email || resetSending}>{copy.reset[lang]}</button>
              <Feedback message={resetMessage} />
            </div>
          </div>
        </details>
      </section>

      <section className={sectionClass} aria-labelledby='account-watchlist'>
        <h2 ref={watchHeading} tabIndex={-1} id='account-watchlist' className={headingClass}>
          {copy.watchlist[lang]}{!watchlistLoading && <> · {watchlist.length}</>}
        </h2>
        {watchlistLoading ? <p role='status' className='text-sm'>{copy.loading[lang]}</p> : (
          watchlist.length === 0 ? (
            <>
              <p className='text-sm text-neutral-muted'>{copy.emptyWatchlist[lang]}</p>
              <div className='flex flex-wrap gap-3'>
                <Link href='/counties' className='audit-receipt'>{copy.findCounty[lang]}</Link>
                <Link href='/budget' className='audit-receipt'>{copy.viewBudget[lang]}</Link>
              </div>
            </>
          ) : (
            <ul className='divide-y divide-neutral-border'>
              {watchlist.map(item => (
                <li key={item.id} className='flex flex-wrap items-center justify-between gap-x-4 py-2'>
                  <Link href={item.item_type === 'county' ? `/counties/${item.item_id}` : '/budget'}
                    className='audit-receipt min-w-0 break-words font-semibold'>{item.label}</Link>
                  <div className='flex flex-wrap items-center gap-2'>
                    {typeof item.notify === 'boolean' && (
                      <span className='text-sm text-neutral-muted'>
                        {item.notify ? copy.alertsOn[lang] : copy.alertsOff[lang]}
                      </span>
                    )}
                    <button type='button' className='audit-control' disabled={watchRemoval !== null}
                      aria-label={copy.removeItem[lang].replace('{item}', item.label)}
                      onClick={() => void removeItem(item.id)}>{copy.remove[lang]}</button>
                  </div>
                </li>
              ))}
            </ul>
          )
        )}
        {watchError && <p role='alert' className='text-sm text-signal-alarm'>{copy.removeError[lang]}</p>}
      </section>

      <section className={sectionClass} aria-labelledby='account-alerts'>
        <div className='flex flex-wrap items-center justify-between gap-2'>
          <h2 ref={alertsHeading} tabIndex={-1} id='account-alerts' className={headingClass}>{copy.alerts[lang]}</h2>
          {alerts?.some(alert => !alert.read) && (
            <button type='button' className='audit-control' disabled={marking !== null}
              onClick={() => void markRead('all')}>{copy.markAllRead[lang]}</button>
          )}
        </div>
        {alertsLoadError ? (
          <div className='space-y-2'>
            <p role='alert' className='text-sm text-signal-alarm'>{copy.alertsLoadError[lang]}</p>
            <button type='button' className='audit-control' onClick={() => void readAlerts()}>{copy.tryAgain[lang]}</button>
          </div>
        ) : alerts === null ? <p role='status' className='text-sm'>{copy.loading[lang]}</p> : (
          alerts.length === 0 ? <p className='text-sm text-neutral-muted'>{copy.emptyAlerts[lang]}</p> : (
            <ul className='divide-y divide-neutral-border'>
              {alerts.map(alert => (
                <li key={alert.id} className='space-y-1 py-3'>
                  <p className='break-words font-semibold'>{alert.title}</p>
                  {alert.body && <p className='break-words text-sm text-neutral-muted'>{alert.body}</p>}
                  <div className='flex flex-wrap items-center gap-2'>
                    {Number.isFinite(Date.parse(alert.created_at)) && (
                      <time dateTime={alert.created_at} className='text-sm text-neutral-muted'>
                        {new Date(alert.created_at).toLocaleDateString(lang === 'sw' ? 'sw-KE' : 'en-KE', {
                          day: 'numeric', month: 'short', year: 'numeric',
                        })}
                      </time>
                    )}
                    {!alert.read && (
                      <>
                        <span className='text-sm font-semibold'>{copy.unread[lang]}</span>
                        <button type='button' className='audit-control' disabled={marking !== null}
                          onClick={() => void markRead(alert.id)}>{copy.markRead[lang]}</button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )
        )}
        {alertsSaveError && <p role='alert' className='text-sm text-signal-alarm'>{copy.alertsSaveError[lang]}</p>}
      </section>

      <AccountDataActions accountId={accountId} />
    </div>
  );
}
