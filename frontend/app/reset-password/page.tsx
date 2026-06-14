'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  ShieldCheck,
} from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useRef, useState } from 'react';

/* ── Minimum password requirements ── */
function getPasswordStrength(pw: string) {
  const checks = [
    { label: 'At least 8 characters', met: pw.length >= 8 },
    { label: 'Contains a number', met: /\d/.test(pw) },
    { label: 'Contains uppercase letter', met: /[A-Z]/.test(pw) },
    { label: 'Contains lowercase letter', met: /[a-z]/.test(pw) },
  ];
  return checks;
}

function ResetPasswordForm() {
  const { refreshUser, isAuthenticated, isLoading: authLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const linkError = searchParams.get('error');
  // PKCE recovery code, forwarded by /auth/callback under the query
  // parameter name ``recovery`` (not ``code``) — this is critical:
  // the browser Supabase SDK auto-detects ``?code=`` on page load
  // and would exchange it itself, creating a session behind our
  // back. Forwarding under ``recovery`` keeps the SDK's
  // ``_isPKCECallback`` check returning false. See
  // /auth/callback/route.ts for the full reasoning. The form-submit
  // handler then POSTs this value as ``code`` to
  // /api/auth/reset-password, which runs on the server with
  // ``detectSessionInUrl: false`` and is the only place the
  // exchange actually happens.
  const recoveryCode = searchParams.get('recovery');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  // Form-submit error only — the URL `?error=` param flows through
  // its own UI branch below (see `linkError && !isAuthenticated`
  // ternary). Don't seed this from linkError or the in-form error
  // panel will show the URL leftover instead of the actual submit
  // failure once the user starts interacting.
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);
  // Synchronous ref-based gate to block double submission. The
  // ``isSubmitting`` state alone isn't enough: ``setIsSubmitting(true)``
  // is async, so a fast double-tap (or the iOS quick-tap that fires
  // both touchstart-derived and click events) slips past the
  // button's ``disabled`` flag before React re-renders, and BOTH
  // submits race in supabase.auth.updateUser. The first changes the
  // password successfully; the second hits the API with the same
  // body and returns ``code: same_password`` because the password
  // is already this value. Net effect for the user: their password
  // DID change, but they see a misleading "should be different"
  // error and have to retry-and-fail to realise it's done.
  //
  // This guard was originally landed in PR #87 but only that PR's
  // first commit (UI rendering fix) actually merged — the followup
  // commits including this gate sat on the closed branch. Bringing
  // it back here so it actually ships.
  const submittingRef = useRef(false);

  const strength = getPasswordStrength(password);
  const allMet = strength.every((c) => c.met);
  const passwordsMatch = password === confirmPassword && confirmPassword.length > 0;

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      // Hard-stop if a previous submit is still in flight. The ref
      // mutates synchronously (unlike ``isSubmitting``'s state
      // update) so it blocks the second event of a fast double-tap
      // before either submit reaches updateUser. See ref's defining
      // comment for the full failure mode this guards against.
      if (submittingRef.current) return;

      setError('');

      if (!allMet) {
        setError('Password does not meet all requirements.');
        return;
      }
      if (!passwordsMatch) {
        setError('Passwords do not match.');
        return;
      }

      if (!recoveryCode) {
        setError('Reset link is missing its verification code. Please request a new one.');
        return;
      }

      submittingRef.current = true;
      setIsSubmitting(true);
      try {
        // Server-side endpoint exchanges the PKCE code, updates the
        // password, and signs out — all in one request, with a
        // read-only cookie adapter so no auth cookies ever reach
        // the browser. See app/api/auth/reset-password/route.ts.
        // This replaces the previous client-side
        // ``supabase.auth.updateUser({ password })`` flow, which
        // unavoidably ran the GoTrueClient's auto-refresh tick
        // alongside the update and produced the duplicate
        // ``PUT /auth/v1/user`` → ``same_password`` error chain.
        const res = await fetch('/api/auth/reset-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: recoveryCode, password }),
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(
            body.error ||
              'Failed to update password. The link may have expired — please request a new one.'
          );
        }

        setSuccess(true);

        // The /api/auth/reset-password response set fresh
        // ``sb-<ref>-auth-token`` cookies — the user is now
        // logged in with their new password. Refresh the
        // AuthProvider so authUser/profile pick up the new
        // session, then redirect to the homepage. We brief-pause
        // before navigating so the success state is visible long
        // enough to register; this is purely cosmetic — by the
        // time the timer fires, refreshUser has already settled.
        try {
          await refreshUser();
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[reset-password] refreshUser after reset failed', err);
        }
        setTimeout(() => {
          router.replace('/');
        }, 1200);
      } catch (err: any) {
        // Surface the server error verbatim when present —
        // typically "New password should be different from the old
        // password." for the same_password code. Console-log the
        // full object so a future "spinner stuck, no message"
        // report is debuggable from DevTools without round-tripping
        // back to this fix.
        // eslint-disable-next-line no-console
        console.error('[reset-password] reset failed', err);
        setError(
          err?.message ||
            'Failed to update password. The link may have expired — please request a new one.'
        );
      } finally {
        submittingRef.current = false;
        setIsSubmitting(false);
      }
    },
    [password, confirmPassword, allMet, passwordsMatch, recoveryCode, refreshUser, router]
  );

  // If auth is still loading, show spinner
  if (authLoading) {
    return (
      <div className='flex items-center justify-center min-h-[60vh]'>
        <Loader2 className='w-8 h-8 animate-spin text-gov-sage' />
      </div>
    );
  }

  return (
    <div className='min-h-screen bg-gradient-to-b from-gov-cream to-white flex items-center justify-center px-4 py-16'>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className='w-full max-w-md'>
        {/* Card */}
        <div className='bg-white dark:bg-surface-base rounded-2xl shadow-xl border border-gov-sage/10 overflow-hidden'>
          {/* Header band */}
          <div className='bg-gradient-to-r from-gov-dark to-gov-forest px-6 py-8 text-center'>
            <div className='w-14 h-14 rounded-2xl bg-white/10 flex items-center justify-center mx-auto mb-4 border border-white/20'>
              <ShieldCheck className='w-7 h-7 text-gov-gold' />
            </div>
            <h1 className='text-xl font-bold text-white'>
              {success ? 'Password Updated' : 'Choose a New Password'}
            </h1>
            <p className='text-white/60 text-sm mt-2'>
              {success
                ? 'Signing you in with your new password…'
                : 'Enter your new password below. Make it strong and unique.'}
            </p>
          </div>

          <div className='p-6'>
            {/* ── Success state ── */}
            {success ? (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className='text-center'>
                <CheckCircle2 className='w-16 h-16 mx-auto text-gov-sage mb-4' />
                <p className='text-gov-forest/70 dark:text-emerald-100/70 text-sm mb-2'>
                  Your password has been updated and you&apos;re signed in. Taking you to the
                  homepage…
                </p>
                <div className='flex items-center justify-center gap-2 text-gov-forest/50 dark:text-emerald-100/50 text-xs mt-4'>
                  <Loader2 className='w-3.5 h-3.5 animate-spin' />
                  Redirecting
                </div>
              </motion.div>
            ) : linkError && !isAuthenticated ? (
              /* ── Link-error state (expired/invalid token) ── */
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                className='text-center'>
                <AlertCircle className='w-16 h-16 mx-auto text-gov-copper/60 mb-4' />
                <p className='text-gov-copper text-sm font-medium mb-2'>{linkError}</p>
                <p className='text-gov-forest/50 dark:text-emerald-100/50 text-xs mb-6'>
                  Password reset links expire after 1 hour for security.
                </p>
                <Link
                  href='/'
                  className='inline-flex items-center gap-2 px-6 py-3 bg-gov-sage text-white font-semibold rounded-xl hover:bg-gov-sage/90 transition-colors shadow-md'>
                  Back to Homepage
                  <ArrowRight className='w-4 h-4' />
                </Link>
              </motion.div>
            ) : (
              /* ── Password form ── */
              <form onSubmit={handleSubmit} className='space-y-5'>
                {/* New Password */}
                <div>
                  <label className='block text-xs font-semibold uppercase tracking-wider text-gov-forest/50 dark:text-emerald-100/50 mb-1.5'>
                    New Password
                  </label>
                  <div className='relative'>
                    <Lock className='absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gov-forest/30 dark:text-emerald-100/30' />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      required
                      minLength={8}
                      value={password}
                      onChange={(e) => {
                        setPassword(e.target.value);
                        setError('');
                      }}
                      placeholder='Enter new password'
                      className='w-full pl-10 pr-12 py-3 rounded-xl bg-gov-cream/40 dark:bg-surface-sunken border border-gov-sage/20 text-gov-dark dark:text-white placeholder:text-gov-forest/30 dark:text-emerald-100/30 focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-transparent transition-all'
                      autoComplete='new-password'
                    />
                    <button
                      type='button'
                      onClick={() => setShowPassword(!showPassword)}
                      className='absolute right-3 top-1/2 -translate-y-1/2 text-gov-forest/30 dark:text-emerald-100/30 hover:text-gov-forest/60 dark:text-emerald-100/60 transition-colors'>
                      {showPassword ? <EyeOff className='w-4 h-4' /> : <Eye className='w-4 h-4' />}
                    </button>
                  </div>
                </div>

                {/* Password strength indicators */}
                {password.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    className='space-y-1.5'>
                    {strength.map((check) => (
                      <div key={check.label} className='flex items-center gap-2 text-xs'>
                        <div
                          className={`w-1.5 h-1.5 rounded-full transition-colors ${
                            check.met ? 'bg-gov-sage' : 'bg-gov-forest/20'
                          }`}
                        />
                        <span
                          className={
                            check.met ? 'text-gov-sage font-medium' : 'text-gov-forest/40 dark:text-emerald-100/40'
                          }>
                          {check.label}
                        </span>
                      </div>
                    ))}
                  </motion.div>
                )}

                {/* Confirm Password */}
                <div>
                  <label className='block text-xs font-semibold uppercase tracking-wider text-gov-forest/50 dark:text-emerald-100/50 mb-1.5'>
                    Confirm Password
                  </label>
                  <div className='relative'>
                    <Lock className='absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gov-forest/30 dark:text-emerald-100/30' />
                    <input
                      type={showConfirm ? 'text' : 'password'}
                      required
                      minLength={8}
                      value={confirmPassword}
                      onChange={(e) => {
                        setConfirmPassword(e.target.value);
                        setError('');
                      }}
                      placeholder='Re-enter new password'
                      className={`w-full pl-10 pr-12 py-3 rounded-xl bg-gov-cream/40 dark:bg-surface-sunken border text-gov-dark dark:text-white placeholder:text-gov-forest/30 dark:text-emerald-100/30 focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:border-transparent transition-all ${
                        confirmPassword.length > 0 && !passwordsMatch
                          ? 'border-gov-copper/40'
                          : confirmPassword.length > 0 && passwordsMatch
                            ? 'border-gov-sage/40'
                            : 'border-gov-sage/20'
                      }`}
                      autoComplete='new-password'
                    />
                    <button
                      type='button'
                      onClick={() => setShowConfirm(!showConfirm)}
                      className='absolute right-3 top-1/2 -translate-y-1/2 text-gov-forest/30 dark:text-emerald-100/30 hover:text-gov-forest/60 dark:text-emerald-100/60 transition-colors'>
                      {showConfirm ? <EyeOff className='w-4 h-4' /> : <Eye className='w-4 h-4' />}
                    </button>
                  </div>
                  {confirmPassword.length > 0 && !passwordsMatch && (
                    <p className='text-gov-copper text-xs mt-1.5'>Passwords do not match</p>
                  )}
                </div>

                {/* Error — show whenever an in-form submit fails.
                    Pre-fix this was gated on `!linkError`, which
                    silently hid the actual same_password / weak-
                    password error from Supabase whenever the URL
                    still carried the original ``?error=`` token-
                    exchange parameter. linkError gets its own
                    dedicated UI branch above (the
                    ``linkError && !isAuthenticated`` ternary), so
                    once we're rendering the form, in-form errors
                    are always meaningful. */}
                <AnimatePresence>
                  {error && (
                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      className='flex items-start gap-2 p-3 rounded-xl bg-gov-copper/10 border border-gov-copper/20 text-gov-copper text-sm'>
                      <AlertCircle className='w-4 h-4 mt-0.5 flex-shrink-0' />
                      <span>{error}</span>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Submit */}
                <button
                  type='submit'
                  disabled={isSubmitting || !allMet || !passwordsMatch}
                  className='flex items-center justify-center gap-2 w-full py-3.5 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-gov-sage/40 focus:ring-offset-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg'>
                  {isSubmitting ? (
                    <Loader2 className='w-5 h-5 animate-spin' />
                  ) : (
                    <>
                      Reset Password
                      <ArrowRight className='w-4 h-4' />
                    </>
                  )}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Security note */}
        <p className='text-center text-gov-forest/30 dark:text-emerald-100/30 text-xs mt-6'>
          For your security, password reset links expire after 1 hour.
          <br />
          If you didn&apos;t request this reset, you can safely ignore this page.
        </p>
      </motion.div>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className='flex items-center justify-center min-h-screen'>
          <Loader2 className='w-8 h-8 animate-spin text-gov-sage' />
        </div>
      }>
      <ResetPasswordForm />
    </Suspense>
  );
}
