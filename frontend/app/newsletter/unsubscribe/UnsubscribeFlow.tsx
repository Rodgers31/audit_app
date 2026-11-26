'use client';

import { getApiBase } from '@/lib/api/base';
import { useLang } from '@/lib/i18n/LangProvider';
import { ChevronLeft } from 'lucide-react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useEffect, useId, useRef, useState, type FormEvent, type ReactNode } from 'react';
import styles from '../../reset-password/ResetPassword.module.css';
import { unsubscribeMessages } from './messages';

type Message = keyof typeof unsubscribeMessages;
type SignedLink = { email: string; token: string };
type Step = 'request' | 'confirm' | 'requested' | 'unsubscribed';
const REQUEST_TIMEOUT_MS = 12_000;

function UnsubscribePageFrame({ title, children }: { title: Message; children: ReactNode }) {
  const { lang } = useLang();
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className={styles.page}>
      <h1 id={headingId} className='font-display text-2xl font-bold leading-tight sm:text-3xl'>
        {unsubscribeMessages[title][lang]}
      </h1>
      {children}
      <Link href='/' className={`audit-receipt mt-3 gap-1 font-semibold text-gov-sage ${styles.home}`}>
        <ChevronLeft size={16} aria-hidden='true' />{unsubscribeMessages.home[lang]}
      </Link>
    </section>
  );
}

export function LoadingUnsubscribe() {
  const { lang } = useLang();
  return <UnsubscribePageFrame title='title'>
    <p role='status' className='mt-3 text-sm text-neutral-muted'>{unsubscribeMessages.loading[lang]}</p>
  </UnsubscribePageFrame>;
}

function RequestForm({ link, unusable }: { link: SignedLink | null; unusable: boolean }) {
  const { lang } = useLang();
  const t = (key: Message) => unsubscribeMessages[key][lang];
  const emailId = useId();
  const helpId = useId();
  const input = useRef<HTMLInputElement>(null);
  const result = useRef<HTMLParagraphElement>(null);
  const request = useRef<AbortController | null>(null);
  const [step, setStep] = useState<Step>(link ? 'confirm' : 'request');
  const [address, setAddress] = useState('');
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<Message | null>(unusable ? 'expired' : null);

  useEffect(() => () => {
    const current = request.current;
    request.current = null;
    current?.abort();
  }, []);

  useEffect(() => {
    if (step === 'requested' || step === 'unsubscribed') result.current?.focus();
    if (step === 'request' && notice === 'expired' && link) input.current?.focus();
  }, [step, notice, link]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (request.current) return;
    const confirming = step === 'confirm' && link !== null;
    const controller = new AbortController();
    request.current = controller;
    setPending(true);
    setNotice(null);
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const action = confirming ? 'unsubscribe-verify' : 'unsubscribe-request';
      const version = process.env.NEXT_PUBLIC_API_VERSION || 'v1';
      const response = await fetch(`${getApiBase()}/api/${version}/newsletter/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        referrerPolicy: 'no-referrer',
        signal: controller.signal,
        body: JSON.stringify(confirming ? link : { email: address.trim() }),
      });
      if (request.current !== controller) return;
      controller.signal.throwIfAborted();
      if (confirming && (response.status === 403 || response.status === 422)) {
        setStep('request');
        setNotice('expired');
        return;
      }
      if (!response.ok) throw new Error('Unsubscribe request failed');
      const payload = await response.json() as { status?: string } | null;
      if (request.current !== controller) return;
      controller.signal.throwIfAborted();
      if (confirming && ['unsubscribed', 'already_unsubscribed', 'not_found'].includes(payload?.status ?? '')) {
        setStep('unsubscribed');
      } else if (!confirming && response.status === 202 && payload?.status === 'requested') {
        setStep('requested');
      } else {
        throw new Error('Unexpected unsubscribe response');
      }
    } catch {
      if (request.current === controller) setNotice(confirming ? 'confirmError' : 'requestError');
    } finally {
      window.clearTimeout(timer);
      if (request.current === controller) {
        request.current = null;
        setPending(false);
      }
    }
  }

  return (
    <UnsubscribePageFrame title={step === 'unsubscribed' ? 'doneTitle' : 'title'}>
      {step === 'requested' || step === 'unsubscribed' ? (
        <p ref={result} tabIndex={-1} role='status' className='mt-3 text-sm text-neutral-text'>
          {t(step === 'requested' ? 'requested' : 'done')}
        </p>
      ) : (
        <>
          <p id={helpId} className='mt-3 text-sm text-neutral-muted'>{t(step === 'confirm' ? 'confirmPrompt' : 'help')}</p>
          <form onSubmit={submit} aria-busy={pending} className='mt-4 space-y-3'>
            {notice && <p role='alert' className='text-sm text-signal-alarm'>{t(notice)}</p>}
            {step === 'request' && <div className='space-y-1'>
              <label htmlFor={emailId} className='block text-sm font-semibold'>{t('email')}</label>
              <input id={emailId} ref={input} aria-describedby={helpId} type='email' autoComplete='email' required maxLength={254}
                value={address} onChange={event => setAddress(event.target.value)} placeholder='you@example.com'
                className='min-h-11 w-full rounded border border-neutral-muted bg-surface-elevated px-3 py-2 text-base text-neutral-text placeholder:text-neutral-muted' />
            </div>}
            <button type='submit' disabled={pending} className={`audit-control ${styles.save}`}>
              {t(step === 'confirm' ? pending ? 'confirming' : 'confirm' : pending ? 'sending' : 'send')}
            </button>
          </form>
        </>
      )}
    </UnsubscribePageFrame>
  );
}

export default function UnsubscribeFlow() {
  const params = useSearchParams();
  const email = params.get('email') || '';
  const token = params.get('token') || '';
  const link = email && /^[a-f0-9]{64}$/.test(token) ? { email, token } : null;
  return <RequestForm key={JSON.stringify([email, token])} link={link} unusable={!!(email || token) && !link} />;
}
