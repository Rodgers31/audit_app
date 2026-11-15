'use client';

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import SmartBackLink from '@/lib/navigation/SmartBackLink';
import SectionNavigation, { type PageSection } from './SectionNavigation';

const PARENTS: Readonly<Record<string, { href: string; label: TranslationKey }>> = {
  '/counties/': { href: '/counties', label: 'shell.counties' },
  '/accountability/': { href: '/audits', label: 'shell.audits' },
  '/learn/': { href: '/learn', label: 'shell.learn' },
  '/sources/': { href: '/sources', label: 'shell.sources' },
  '/reports/': { href: '/sources', label: 'shell.sources' },
};

interface PageShellProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  back?: { href: string; label: string };
  sections?: readonly PageSection[];
  actions?: ReactNode;
  breadcrumbs?: boolean;
}

export default function PageShell({ title, subtitle, children, className = '', back, sections, actions, breadcrumbs = true }: PageShellProps) {
  const pathname = usePathname() ?? '';
  const { t } = useLang();
  const parent = Object.entries(PARENTS).find(([path]) => pathname.startsWith(path))?.[1];
  const content = <div className={`page-shell-content min-w-0 space-y-6 ${className}`}>{children}</div>;

  return (
    <div className='relative min-h-screen bg-gov-sand dark:bg-surface-sunken'>
      <header className='border-b border-neutral-border bg-gov-dark pt-[var(--public-header-height)] text-white'>
        <div className='mx-auto max-w-screen-xl px-4 py-4 sm:px-6 md:py-6'>
          {back && (
            <SmartBackLink href={back.href} className='inline-flex min-h-11 items-center gap-2 text-sm text-gov-cream underline-offset-4 hover:underline'>
              <ArrowLeft size={16} aria-hidden='true' /> {back.label}
            </SmartBackLink>
          )}
          {breadcrumbs && (
            <nav aria-label={t('shell.crumbs')} className={`text-audit-label text-[color:var(--gold-on-dark)] ${back ? 'hidden lg:block' : ''}`}>
              <ol className='flex flex-wrap items-center gap-x-2'>
                <li><Link href={parent?.href ?? '/'} className='inline-flex min-h-11 items-center underline-offset-4 hover:underline'>{parent ? t(parent.label) : 'AuditGava'}</Link></li>
                <li aria-hidden='true'>›</li>
                <li aria-current='page'>{title}</li>
              </ol>
            </nav>
          )}
          <div className='flex min-w-0 items-start justify-between gap-2'>
            <h1 className='audit-figure min-w-0 break-words text-audit-title uppercase text-white'>{title}</h1>
            {actions}
          </div>
          {subtitle && <p className='mt-2 max-w-[70ch] text-base text-gov-cream'>{subtitle}</p>}
        </div>
      </header>
      <div className='mx-auto max-w-screen-xl px-4 py-5 sm:px-6 md:py-8'>
        {sections?.length ? <SectionNavigation sections={sections}>{content}</SectionNavigation> : content}
      </div>
    </div>
  );
}
