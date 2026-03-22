'use client';

import { Heart, Mail } from 'lucide-react';
import Link from 'next/link';

const FOOTER_LINKS = [
  { label: 'About', href: '/about' },
  { label: 'Privacy Policy', href: '/privacy' },
  { label: 'Terms of Use', href: '/terms' },
];

const EXTERNAL_LINKS = [
  {
    label: 'Contact',
    href: 'mailto:auditgava@gmail.com',
    icon: Mail,
  },
];

export default function Footer() {
  return (
    <footer className='relative z-[1] bg-gov-dark border-t border-gov-sage/15'>
      <div className='max-w-[1340px] mx-auto px-4 sm:px-6 py-10 sm:py-12'>
        {/* ── Top row: Brand + links ── */}
        <div className='flex flex-col sm:flex-row sm:items-start sm:justify-between gap-8'>
          {/* Brand */}
          <div className='space-y-3 max-w-xs'>
            <Link href='/' className='inline-flex items-center gap-2 group'>
              <span className='text-lg font-display text-white group-hover:text-gov-gold transition-colors'>
                AuditGava
              </span>
            </Link>
            <p className='text-white/50 text-xs leading-relaxed'>
              A free, open-source civic technology platform tracking Kenya&apos;s public finances
              using official government data.
            </p>
          </div>

          {/* Navigation links */}
          <div className='flex flex-wrap gap-x-8 gap-y-3'>
            {FOOTER_LINKS.map(({ label, href }) => (
              <Link
                key={href}
                href={href}
                className='text-[13px] text-white/60 hover:text-gov-sage transition-colors'>
                {label}
              </Link>
            ))}
          </div>

          {/* External / social links */}
          <div className='flex items-center gap-4'>
            {EXTERNAL_LINKS.map(({ label, href, icon: Icon }) => (
              <a
                key={label}
                href={href}
                target={href.startsWith('mailto:') ? undefined : '_blank'}
                rel='noopener noreferrer'
                aria-label={label}
                className='w-9 h-9 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center text-white/50 hover:text-gov-sage hover:border-gov-sage/30 transition-all'>
                <Icon className='w-4 h-4' />
              </a>
            ))}
          </div>
        </div>

        {/* ── Divider ── */}
        <div className='mt-8 pt-6 border-t border-white/10'>
          <div className='flex flex-col sm:flex-row items-center justify-between gap-3 text-[11px] text-white/40'>
            <p>&copy; {new Date().getFullYear()} AuditGava. All rights reserved.</p>
            <p className='flex items-center gap-1'>
              Built with <Heart className='w-3 h-3 fill-current text-red-400' /> for transparency
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
