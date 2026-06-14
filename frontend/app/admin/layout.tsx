/**
 * /admin – shared shell for the admin section.
 *
 * Wraps every admin route in <AdminGuard> (third defence layer behind
 * Next.js middleware and backend ``require_admin``) and renders a
 * sticky pill-style sub-nav that floats just below the main app
 * navigation. Pages themselves provide their own dark hero band via
 * <PageShell> so the typography and animation match the rest of the
 * public site (about, debt, budget, etc.).
 */
'use client';

import { AdminGuard } from '@/lib/auth/admin';
import {
  Activity,
  BarChart3,
  History,
  ListChecks,
  PlayCircle,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const NAV_ITEMS = [
  { href: '/admin', label: 'Overview', icon: BarChart3, exact: true },
  { href: '/admin/users', label: 'Users', icon: Users },
  { href: '/admin/ingestion', label: 'Ingestion', icon: ListChecks },
  { href: '/admin/etl', label: 'ETL Schedule', icon: PlayCircle },
  { href: '/admin/audit-log', label: 'Audit Log', icon: History },
  { href: '/status', label: 'Pipeline Status', icon: Activity },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <AdminGuard>
      <AdminNav />
      {children}
    </AdminGuard>
  );
}

function AdminNav() {
  const pathname = usePathname();

  const isActive = (href: string, exact?: boolean) =>
    exact ? pathname === href : pathname.startsWith(href);

  return (
    <div className='sticky top-[72px] z-30 bg-gov-dark/95 backdrop-blur-md border-b border-gov-forest/40 shadow-md'>
      <div className='max-w-[1340px] mx-auto px-5 lg:px-8'>
        <div className='flex items-center gap-1.5 sm:gap-2 overflow-x-auto py-2.5 scrollbar-hide'>
          {NAV_ITEMS.map(({ href, label, icon: Icon, exact }) => {
            const active = isActive(href, exact);
            return (
              <Link
                key={href}
                href={href}
                className={`inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold transition-all whitespace-nowrap ${
                  active
                    ? 'bg-gov-gold/20 text-gov-gold ring-1 ring-inset ring-gov-gold/40 shadow-sm'
                    : 'text-white/70 hover:text-white hover:bg-white/10 ring-1 ring-inset ring-transparent'
                }`}>
                <Icon className='w-3.5 h-3.5' />
                {label}
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
}
