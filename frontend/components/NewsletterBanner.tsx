'use client';

import { subscribeNewsletter } from '@/lib/api/auth';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { motion } from 'framer-motion';
import { CheckCircle2, Info, Loader2, Mail, Send } from 'lucide-react';
import { useCallback, useState } from 'react';

type Status =
  | 'idle'
  | 'submitting'
  | 'subscribed'
  | 'resubscribed'
  | 'already_subscribed'
  | 'error';

const STATUS_MESSAGES: Record<
  string,
  { icon: typeof CheckCircle2; textKey: TranslationKey; color: string }
> = {
  subscribed: {
    icon: CheckCircle2,
    textKey: 'home.newsletter.subscribed',
    color: 'text-green-300',
  },
  resubscribed: {
    icon: CheckCircle2,
    textKey: 'home.newsletter.resubscribed',
    color: 'text-green-300',
  },
  already_subscribed: {
    icon: Info,
    textKey: 'home.newsletter.already',
    color: 'text-amber-300',
  },
};

/**
 * Newsletter email capture banner.
 * No auth required — anyone can subscribe.
 * Drop into any page (dashboard footer, learn page, etc.)
 */
export default function NewsletterBanner() {
  const { t } = useLang();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!email) return;
      setStatus('submitting');
      setErrorMsg('');
      try {
        const result = await subscribeNewsletter(email);
        setStatus(result.status);
        if (result.status === 'subscribed') setEmail('');
      } catch (err: any) {
        setStatus('error');
        setErrorMsg(err?.message || t('home.newsletter.generic_error'));
      }
    },
    [email, t]
  );

  const statusInfo = STATUS_MESSAGES[status];

  return (
    <section className='relative overflow-hidden py-10 sm:py-14'>
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: '-40px' }}
        transition={{ duration: 0.6 }}
        className='max-w-xl mx-auto px-6'>
        <div className='bg-gov-forest/90 backdrop-blur-lg border border-gov-sage/30 rounded-3xl p-6 sm:p-8 shadow-xl text-center'>
          <div className='w-12 h-12 rounded-2xl bg-gov-sage/20 flex items-center justify-center mx-auto mb-4 border border-gov-sage/30'>
            <Mail className='w-6 h-6 text-gov-sage' />
          </div>
          <h3 className='font-display text-xl sm:text-2xl text-white mb-2'>{t('home.newsletter.title')}</h3>
          <p className='text-white/60 text-sm mb-6'>{t('home.newsletter.body')}</p>

          {statusInfo ? (
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className={`flex items-center justify-center gap-2 ${statusInfo.color} font-semibold text-sm`}>
              <statusInfo.icon className='w-5 h-5' />
              {t(statusInfo.textKey)}
            </motion.div>
          ) : (
            <form onSubmit={handleSubmit} className='flex flex-col sm:flex-row gap-3'>
              <div className='relative flex-1'>
                <Mail className='absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30' />
                <input
                  type='email'
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder={t('home.newsletter.placeholder')}
                  className='w-full pl-10 pr-4 py-3 rounded-xl bg-white/10 border border-white/15 text-white placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-gov-sage/50 transition-all'
                />
              </div>
              <button
                type='submit'
                disabled={status === 'submitting'}
                className='flex items-center justify-center gap-2 px-6 py-3 rounded-xl bg-gov-sage text-white font-semibold hover:bg-gov-sage/90 active:scale-[0.98] transition-all disabled:opacity-60 shadow-lg whitespace-nowrap'>
                {status === 'submitting' ? (
                  <Loader2 className='w-4 h-4 animate-spin' />
                ) : (
                  <>
                    <Send className='w-4 h-4' />
                    {t('home.newsletter.subscribe')}
                  </>
                )}
              </button>
            </form>
          )}

          {status === 'error' && errorMsg && (
            <p className='text-gov-copper text-xs mt-3'>{errorMsg}</p>
          )}
        </div>
      </motion.div>
    </section>
  );
}
