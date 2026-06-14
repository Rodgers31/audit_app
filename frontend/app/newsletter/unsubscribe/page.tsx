'use client';

import { apiClient } from '@/lib/api/axios';
import { motion } from 'framer-motion';
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2, Mail, MailX } from 'lucide-react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useState } from 'react';

type Status = 'confirm' | 'submitting' | 'done' | 'already' | 'not_found' | 'error';

function UnsubscribeForm() {
  const params = useSearchParams();
  const email = params.get('email') || '';
  const token = params.get('token') || '';

  const [status, setStatus] = useState<Status>(email && token ? 'confirm' : 'error');
  const [errorMsg, setErrorMsg] = useState(
    !email || !token ? 'Invalid unsubscribe link — the email or token is missing.' : ''
  );

  const handleUnsubscribe = useCallback(async () => {
    setStatus('submitting');
    setErrorMsg('');
    try {
      const { data } = await apiClient.post('/newsletter/unsubscribe-verify', { email, token });
      if (data.status === 'unsubscribed') {
        setStatus('done');
      } else if (data.status === 'already_unsubscribed') {
        setStatus('already');
      } else if (data.status === 'not_found') {
        setStatus('not_found');
      } else {
        setStatus('done');
      }
    } catch (err: any) {
      setStatus('error');
      setErrorMsg(
        err?.response?.data?.detail ||
          err?.message ||
          'Something went wrong. Please try again or contact support.'
      );
    }
  }, [email, token]);

  return (
    <div className='relative min-h-screen flex items-center justify-center px-4 py-20'>
      {/* Background */}
      <div
        className='absolute inset-0'
        style={{ backgroundColor: '#F5F0E8', zIndex: 0 }}
        aria-hidden='true'
      />

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className='relative z-10 w-full max-w-md'>
        <div className='bg-gov-forest/95 backdrop-blur-lg border border-gov-sage/30 rounded-3xl p-8 shadow-xl text-center'>
          {/* ── Confirm state ── */}
          {status === 'confirm' && (
            <>
              <div className='w-14 h-14 rounded-2xl bg-gov-copper/20 flex items-center justify-center mx-auto mb-5 border border-gov-copper/30'>
                <MailX className='w-7 h-7 text-gov-copper' />
              </div>
              <h1 className='font-display text-2xl text-white mb-2'>Unsubscribe</h1>
              <p className='text-white/60 text-sm mb-2'>Are you sure you want to unsubscribe?</p>
              <p className='text-white/80 text-sm font-medium mb-6 break-all'>{email}</p>
              <p className='text-white/50 text-xs mb-6'>
                You will no longer receive weekly audit &amp; budget digests.
              </p>
              <button
                onClick={handleUnsubscribe}
                className='w-full flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gov-copper text-white font-semibold hover:bg-gov-copper/90 active:scale-[0.98] transition-all shadow-lg'>
                <MailX className='w-4 h-4' />
                Yes, unsubscribe me
              </button>
              <Link
                href='/'
                className='inline-flex items-center gap-1 mt-4 text-gov-sage text-sm hover:underline'>
                <ArrowLeft className='w-3 h-3' />
                No, take me back
              </Link>
            </>
          )}

          {/* ── Submitting ── */}
          {status === 'submitting' && (
            <div className='py-8'>
              <Loader2 className='w-8 h-8 text-gov-sage animate-spin mx-auto mb-4' />
              <p className='text-white/60 text-sm'>Processing your request…</p>
            </div>
          )}

          {/* ── Done ── */}
          {status === 'done' && (
            <>
              <div className='w-14 h-14 rounded-2xl bg-green-900/30 flex items-center justify-center mx-auto mb-5 border border-green-700/30'>
                <CheckCircle2 className='w-7 h-7 text-green-400' />
              </div>
              <h1 className='font-display text-2xl text-white mb-2'>You're unsubscribed</h1>
              <p className='text-white/60 text-sm mb-6'>
                We've removed <strong className='text-white/80'>{email}</strong> from our mailing
                list. You won't receive any more emails from us.
              </p>
              <p className='text-white/40 text-xs mb-6'>
                Changed your mind? You can always re-subscribe from the homepage.
              </p>
              <Link
                href='/'
                className='inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all shadow-lg'>
                <ArrowLeft className='w-4 h-4' />
                Back to Dashboard
              </Link>
            </>
          )}

          {/* ── Already unsubscribed ── */}
          {status === 'already' && (
            <>
              <div className='w-14 h-14 rounded-2xl bg-amber-900/30 flex items-center justify-center mx-auto mb-5 border border-amber-700/30'>
                <Mail className='w-7 h-7 text-amber-400' />
              </div>
              <h1 className='font-display text-2xl text-white mb-2'>Already unsubscribed</h1>
              <p className='text-white/60 text-sm mb-6'>
                <strong className='text-white/80'>{email}</strong> is already unsubscribed. No
                further action needed.
              </p>
              <Link
                href='/'
                className='inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all shadow-lg'>
                <ArrowLeft className='w-4 h-4' />
                Back to Dashboard
              </Link>
            </>
          )}

          {/* ── Not found ── */}
          {status === 'not_found' && (
            <>
              <div className='w-14 h-14 rounded-2xl bg-amber-900/30 flex items-center justify-center mx-auto mb-5 border border-amber-700/30'>
                <AlertTriangle className='w-7 h-7 text-amber-400' />
              </div>
              <h1 className='font-display text-2xl text-white mb-2'>Email not found</h1>
              <p className='text-white/60 text-sm mb-6'>
                We couldn't find <strong className='text-white/80'>{email}</strong> in our
                subscriber list. You may have already been removed.
              </p>
              <Link
                href='/'
                className='inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all shadow-lg'>
                <ArrowLeft className='w-4 h-4' />
                Back to Dashboard
              </Link>
            </>
          )}

          {/* ── Error ── */}
          {status === 'error' && (
            <>
              <div className='w-14 h-14 rounded-2xl bg-gov-copper/20 flex items-center justify-center mx-auto mb-5 border border-gov-copper/30'>
                <AlertTriangle className='w-7 h-7 text-gov-copper' />
              </div>
              <h1 className='font-display text-2xl text-white mb-2'>Something went wrong</h1>
              <p className='text-white/60 text-sm mb-6'>
                {errorMsg || 'This unsubscribe link may be invalid or expired.'}
              </p>
              <Link
                href='/'
                className='inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all shadow-lg'>
                <ArrowLeft className='w-4 h-4' />
                Back to Dashboard
              </Link>
            </>
          )}
        </div>

        {/* Footer attribution */}
        <p className='text-center text-gov-forest/40 dark:text-emerald-100/40 text-xs mt-6'>
          Kenya Public Money Tracker · Government Financial Transparency
        </p>
      </motion.div>
    </div>
  );
}

export default function NewsletterUnsubscribePage() {
  return (
    <Suspense
      fallback={
        <div className='min-h-screen flex items-center justify-center bg-gov-sand'>
          <Loader2 className='w-8 h-8 text-gov-sage animate-spin' />
        </div>
      }>
      <UnsubscribeForm />
    </Suspense>
  );
}
