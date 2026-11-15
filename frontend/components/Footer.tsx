'use client';

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
        <div className='mt-3 grid gap-2 border-t border-neutral-border pt-3 text-sm sm:grid-cols-2'>
          <p>{noticeStart}<Link href='/terms' className='underline underline-offset-4'>{t('shell.terms')}</Link>{noticeEnd}</p>
          <p className='text-xs text-gov-cream/75'>© {new Date().getUTCFullYear()} · {t('shell.footer_independent')}</p>
        </div>
      </div>
    </footer>
  );
}
