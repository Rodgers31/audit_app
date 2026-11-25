'use client';

import { Coffee } from 'lucide-react';
import Link from 'next/link';
import { useLang } from '@/lib/i18n/LangProvider';
import FooterSocialLinks from './FooterSocialLinks';

const FOOTER_LINKS = [
  ['shell.footer_sources', '/sources'],
  ['shell.audits', '/audits'],
  ['shell.about', '/about'],
  ['shell.footer_privacy', '/privacy'],
  ['shell.footer_terms', '/terms'],
  ['shell.newsletter', '/#newsletter'],
] as const;

export default function Footer() {
  const { t } = useLang();
  const [noticeStart, noticeEnd] = t('shell.footer_notice').split('{terms}');
  return (
    <footer className='relative z-[1] border-t border-neutral-border bg-gov-dark text-gov-cream'>
      <div className='mx-auto max-w-screen-xl px-4 py-5 sm:px-6'>
        <div className='grid gap-4 lg:grid-cols-[1.3fr_1fr_1fr]'>
          <div>
            <Link href='/' className='inline-flex min-h-11 items-center font-display text-2xl font-semibold uppercase underline-offset-4 hover:underline'>AuditGava</Link>
            <p className='text-sm'>{t('shell.footer_line')}</p>
          </div>
          <nav aria-label={t('shell.footer')} className='grid grid-cols-2 gap-x-3'>
            {FOOTER_LINKS.map(([label, href]) => <Link key={href} href={href} className='inline-flex min-h-11 items-center border-b border-gov-cream/20 text-sm font-medium underline-offset-4 hover:underline'>{t(label)}</Link>)}
          </nav>
          <div>
            <a href='mailto:auditgava@gmail.com' className='inline-flex min-h-11 items-center text-sm underline-offset-4 hover:underline'>{t('shell.corrections')}: auditgava@gmail.com</a>
            <FooterSocialLinks label={t('shell.footer_social')} />
          </div>
        </div>
        <section
          aria-labelledby='footer-support-title'
          className='mt-7 flex flex-col items-start gap-4 border-l-[3px] border-gov-gold bg-[#1b3528] px-5 py-6 min-[701px]:mt-9 min-[701px]:flex-row min-[701px]:items-center min-[701px]:justify-between min-[701px]:gap-8 lg:px-8'>
          <div className='max-w-[63ch]'>
            <h2
              id='footer-support-title'
              className='font-display text-[27px] font-semibold leading-[1.08] text-gov-cream lg:text-4xl'>
              {t('shell.footer_support_title')}
            </h2>
            <p className='mt-2 text-pretty text-[15px] leading-6 text-[#d6e1d9]'>
              {t('shell.footer_support_message')}
            </p>
          </div>
          <a
            href='https://buymeacoffee.com/auditgava'
            className='inline-flex min-h-[46px] shrink-0 items-center justify-center gap-2.5 rounded bg-[#f0cf81] px-5 py-2.5 text-[15px] font-bold text-gov-dark hover:bg-[#ffe1a2] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white'>
            <Coffee className='h-5 w-5' strokeWidth={1.8} aria-hidden='true' />
            {t('shell.footer_support_link')}
          </a>
        </section>
        <div className='mt-6 grid gap-2 border-t border-neutral-border pt-3 text-sm sm:grid-cols-2'>
          <p>{noticeStart}<Link href='/terms' className='underline underline-offset-4'>{t('shell.terms')}</Link>{noticeEnd}</p>
          <p className='text-xs text-gov-cream/75'>© {new Date().getUTCFullYear()} · {t('shell.footer_independent')}</p>
        </div>
      </div>
    </footer>
  );
}
