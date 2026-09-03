'use client';

import { ArrowUpRight, Mail, ShieldCheck } from 'lucide-react';
import Link from 'next/link';

const FOOTER_LINKS = [
  { label: 'Data & sources', href: '/sources' },
  { label: 'Audit findings', href: '/audits' },
  { label: 'About AuditGava', href: '/about' },
  { label: 'Privacy policy', href: '/privacy' },
  { label: 'Terms of use', href: '/terms' },
];

export default function Footer() {
  return (
    <footer className='relative z-[1] border-t-4 border-gov-copper bg-gov-dark text-white'>
      <div className='mx-auto max-w-[1400px] px-5 py-10 sm:px-6 lg:px-8 lg:py-12'>
        <div className='grid gap-9 lg:grid-cols-[1.25fr_1fr_1fr]'>
          <div className='max-w-lg'>
            <Link
              href='/'
              className='inline-flex border-b border-gov-gold/70 pb-1 font-display text-3xl font-semibold uppercase tracking-[0.02em] text-white hover:text-gov-gold'>
              AuditGava
            </Link>
            <p className='mt-4 max-w-md text-sm leading-6 text-white/62'>
              An independent, open civic platform that connects Kenya&apos;s public-finance figures
              to the official records behind them.
            </p>
            <p className='mt-5 inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-emerald-300'>
              <ShieldCheck className='h-4 w-4' aria-hidden='true' />
              Evidence first · sources remain visible
            </p>
          </div>

          <nav aria-label='Footer navigation'>
            <p className='font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-white/42'>
              Public record
            </p>
            <div className='mt-4 grid gap-2'>
              {FOOTER_LINKS.map(({ label, href }) => (
                <Link
                  key={href}
                  href={href}
                  className='group flex min-h-9 items-center justify-between border-b border-white/12 py-2 text-sm text-white/68 hover:border-gov-gold/60 hover:text-white'>
                  {label}
                  <ArrowUpRight className='h-3.5 w-3.5 text-white/30 group-hover:text-gov-gold' aria-hidden='true' />
                </Link>
              ))}
            </div>
          </nav>

          <div>
            <p className='font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-white/42'>
              Questions or corrections
            </p>
            <a
              href='mailto:auditgava@gmail.com'
              className='mt-4 flex min-h-12 items-center gap-3 border border-white/18 px-4 text-sm font-semibold text-white/78 hover:border-gov-gold hover:text-white'>
              <Mail className='h-4 w-4 text-gov-gold' aria-hidden='true' />
              auditgava@gmail.com
            </a>
            <p className='mt-4 text-xs leading-5 text-white/45'>
              Flag a source mismatch, stale figure, or missing public record. Include the page and
              reporting period when possible.
            </p>
          </div>
        </div>

        <div className='mt-10 flex flex-col gap-3 border-t border-white/14 pt-5 font-mono text-[11px] uppercase tracking-[0.1em] text-white/38 sm:flex-row sm:items-center sm:justify-between'>
          <p>&copy; {new Date().getFullYear()} AuditGava · Republic of Kenya</p>
          <p>Independent civic technology · not a government agency</p>
        </div>
      </div>
    </footer>
  );
}
