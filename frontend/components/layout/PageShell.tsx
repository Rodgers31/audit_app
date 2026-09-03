'use client';

import SmartBackLink from '@/lib/navigation/SmartBackLink';
import { motion, useReducedMotion } from 'framer-motion';
import { ArrowLeft, CheckCircle2, Database } from 'lucide-react';
import { usePathname } from 'next/navigation';
import React from 'react';

interface PageShellProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  back?: { href: string; label: string };
}

function routeLabel(pathname: string) {
  const parts = pathname.split('/').filter(Boolean);
  return parts.length ? parts.join(' / ') : 'dashboard';
}

export default function PageShell({
  title,
  subtitle,
  children,
  className = '',
  back,
}: PageShellProps) {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();

  return (
    <div className='relative min-h-screen bg-gov-sand dark:bg-[#0d1711]'>
      <header className='relative isolate border-b border-neutral-border bg-gov-dark pt-16 text-white'>
        <div aria-hidden='true' className='absolute inset-y-0 left-0 w-1.5 bg-gov-copper' />
        <div className='mx-auto grid max-w-[1400px] gap-6 px-5 py-8 sm:px-6 md:py-10 lg:grid-cols-[180px_minmax(0,1fr)_250px] lg:px-8'>
          <div className='hidden border-r border-white/15 pr-6 lg:block'>
            <p className='font-mono text-[11px] font-medium uppercase tracking-[0.16em] text-white/45'>
              Current record
            </p>
            <p className='mt-3 break-words font-mono text-[11px] uppercase leading-relaxed tracking-[0.08em] text-gov-gold'>
              {routeLabel(pathname)}
            </p>
          </div>

          <motion.div
            initial={false}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.34, ease: [0.22, 1, 0.36, 1] }}
            className='ledger-enter min-w-0'>
            {back && (
              <SmartBackLink
                href={back.href}
                className='mb-4 inline-flex min-h-9 items-center gap-2 border-b border-white/25 pb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-white/70 hover:border-gov-gold hover:text-white'>
                <ArrowLeft size={13} aria-hidden='true' />
                {back.label}
              </SmartBackLink>
            )}
            <p className='mb-2 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-gov-gold lg:hidden'>
              AuditGava / {routeLabel(pathname)}
            </p>
            <h1 className='max-w-4xl font-display text-[2.4rem] font-semibold uppercase leading-[0.95] tracking-[0.01em] text-white sm:text-5xl lg:text-[4.25rem]'>
              {title}
            </h1>
            {subtitle && (
              <p className='mt-4 max-w-3xl text-[15px] leading-6 text-white/68 sm:text-base'>
                {subtitle}
              </p>
            )}
          </motion.div>

          <aside className='flex items-start gap-3 border-t border-white/15 pt-4 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0'>
            <Database className='mt-0.5 h-4 w-4 shrink-0 text-gov-gold' aria-hidden='true' />
            <div>
              <p className='font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-white/48'>
                Evidence standard
              </p>
              <p className='mt-2 text-xs leading-5 text-white/72'>
                Public pages identify official sources and reporting periods wherever figures appear.
              </p>
              <p className='mt-2 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.08em] text-emerald-300'>
                <CheckCircle2 className='h-3.5 w-3.5' aria-hidden='true' />
                Source trail visible
              </p>
            </div>
          </aside>
        </div>

        <div aria-hidden='true' className='relative h-1 bg-white/8'>
          <motion.span
            className='absolute inset-y-0 left-0 w-[28%] origin-left bg-gov-copper'
            initial={reduceMotion ? false : { scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.62, ease: 'easeOut', delay: 0.08 }}
          />
          <span className='absolute left-[28%] top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rotate-45 bg-gov-gold' />
        </div>
      </header>

      <div className='mx-auto max-w-[1400px] px-5 py-7 sm:px-6 sm:py-9 lg:px-8 lg:py-11'>
        <motion.div
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1], delay: 0.08 }}
          className={`ledger-enter ledger-enter-delayed page-shell-content space-y-6 ${className}`}>
          {children}
        </motion.div>
      </div>
    </div>
  );
}
