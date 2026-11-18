'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import { Eye, EyeOff } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { resetMessages } from './messages';
import styles from './ResetPassword.module.css';

function LoadingResetForm() {
  const { lang } = useLang();
  return (
    <div className={styles.page}>
      <p role='status' className='text-sm text-neutral-muted'>{resetMessages.loading[lang]}</p>
    </div>
  );
}

function PasswordField({ id, label, value, showLabel, hideLabel, onChange, describedBy, invalid }: {
  id: string;
  label: string;
  value: string;
  showLabel: string;
  hideLabel: string;
  onChange: (value: string) => void;
  describedBy?: string;
  invalid?: boolean;
}) {
  const [visible, setVisible] = useState(false);

  return (
    <div className='space-y-1'>
      <label htmlFor={id} className='block text-sm font-semibold'>{label}</label>
      <div className={styles.field}>
        <input
          id={id}
          type={visible ? 'text' : 'password'}
          required
          minLength={8}
          maxLength={1024}
          value={value}
          onChange={event => onChange(event.target.value)}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          className={styles.input}
          autoComplete='new-password'
        />
        <button
          type='button'
          aria-label={visible ? hideLabel : showLabel}
          aria-controls={id}
          onClick={() => setVisible(!visible)}
          className={styles.visibility}
        >
          {visible ? <EyeOff size={18} aria-hidden='true' /> : <Eye size={18} aria-hidden='true' />}
        </button>
      </div>
    </div>
  );
}

function ResetPasswordForm() {
  const { refreshUser, isAuthenticated, isLoading: authLoading } = useAuth();
  const { lang } = useLang();
  const t = (key: keyof typeof resetMessages) => resetMessages[key][lang];
  const router = useRouter();
  const searchParams = useSearchParams();
  const linkError = searchParams.get('error');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  // State updates are deferred. Claim the request synchronously to reject a double tap.
  const submittingRef = useRef(false);
  const successHeading = useRef<HTMLHeadingElement>(null);

  const allMet = password.length >= 8 && /\d/.test(password) && /[A-Z]/.test(password) && /[a-z]/.test(password);
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword;
  const mismatch = confirmPassword.length > 0 && !passwordsMatch;

  useEffect(() => {
    if (success && !authLoading) successHeading.current?.focus();
  }, [success, authLoading]);

  const handleSubmit = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      if (submittingRef.current) return;

      setError('');
      if (!allMet) {
        setError(resetMessages.requirements[lang]);
        return;
      }
      if (!passwordsMatch) {
        setError(resetMessages.mismatch[lang]);
        return;
      }

      submittingRef.current = true;
      setIsSubmitting(true);
      try {
        // The server owns the PKCE exchange. The fragment supplies the per-tab selector.
        const selectors = new URLSearchParams(window.location.hash.slice(1)).getAll('recovery-flow');
        const flow = selectors.length === 1 ? selectors[0] : null;
        const res = await fetch('/api/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password, flow }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || resetMessages.failed[lang]);
        }

        setSuccess(true);
        // Refresh the provider after the response commits the new session cookies.
        try {
          await refreshUser();
        } catch {
          // eslint-disable-next-line no-console
          console.warn('[reset-password] session refresh failed');
        }
        setTimeout(() => {
          router.replace('/');
        }, 1200);
      } catch (err: any) {
        setError(err?.message || resetMessages.failed[lang]);
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    [password, allMet, passwordsMatch, refreshUser, router, lang]
  );

  if (authLoading) return <LoadingResetForm />;

  const unusableLink = linkError && !isAuthenticated;
  return (
    <section aria-labelledby='reset-password-title' className={styles.page}>
      <h1 id='reset-password-title' ref={success ? successHeading : undefined} tabIndex={success ? -1 : undefined}
        className='font-display text-2xl font-bold leading-tight sm:text-3xl'>
        {t(success ? 'updated' : unusableLink ? 'invalid' : 'title')}
      </h1>
      {success ? (
        <p role='status' className='mt-3 text-sm text-neutral-muted'>{t('redirecting')}</p>
      ) : unusableLink ? (
        <div className='mt-3 space-y-3 text-sm'>
          <p role='alert' className='text-signal-alarm'>{linkError}</p>
          <p className='text-neutral-muted'>{t('reopen')}</p>
          <Link href='/' className={`audit-control ${styles.home}`}>{t('home')}</Link>
        </div>
      ) : (
        <>
          <p id='reset-password-rules' className='mt-3 text-sm text-neutral-muted'>{t('rules')}</p>
          <p className='mt-1 text-sm text-neutral-muted'>{t('window')}</p>
          <form onSubmit={handleSubmit} aria-busy={isSubmitting} className='mt-4 space-y-3'>
            <PasswordField
              id='reset-password-new' label={t('password')} value={password}
              showLabel={t('showPassword')} hideLabel={t('hidePassword')}
              describedBy='reset-password-rules'
              onChange={value => { setPassword(value); setError(''); }}
            />
            <PasswordField
              id='reset-password-confirm' label={t('confirmation')} value={confirmPassword}
              showLabel={t('showConfirmation')} hideLabel={t('hideConfirmation')}
              invalid={mismatch} describedBy={mismatch ? 'reset-password-mismatch' : undefined}
              onChange={value => { setConfirmPassword(value); setError(''); }}
            />
            {mismatch && <p id='reset-password-mismatch' className='text-sm text-signal-alarm'>{t('mismatch')}</p>}
            {error && <p role='alert' className='text-sm text-signal-alarm'>{error}</p>}
            <button type='submit' disabled={isSubmitting || !allMet || !passwordsMatch}
              className={`audit-control ${styles.save}`}>
              {t(isSubmitting ? 'saving' : 'save')}
            </button>
          </form>
        </>
      )}
    </section>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<LoadingResetForm />}>
      <ResetPasswordForm />
    </Suspense>
  );
}
