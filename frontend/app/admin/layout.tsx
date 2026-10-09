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

import { AdminGuard, useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  Activity,
  BarChart3,
  History,
  ListChecks,
  PlayCircle,
  Send,
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
  { href: '/admin/social', label: 'Social Media', icon: Send },
  { href: '/admin/social/new', label: 'Compose', icon: Send },
  { href: '/admin/social/accounts', label: 'Social accounts', icon: Users },
  { href: '/status', label: 'Pipeline Status', icon: Activity },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAdmin } = useAdmin();
  const { user } = useAuth();
  const actorId = user?.id ?? null;
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!isAdmin || !actorId) {
      void queryClient.cancelQueries({ queryKey: ['admin'] });
      queryClient.removeQueries({ queryKey: ['admin'] });
    }
    return () => {
      // Other admin lanes use the same actor position. Do not cancel a newly
      // mounted next actor while removing the departing actor's private data.
      const previousActor = { queryKey: ['admin'], predicate: (query: { queryKey: readonly unknown[] }) => query.queryKey[2] === actorId };
      void queryClient.cancelQueries(previousActor);
      queryClient.removeQueries(previousActor);
    };
  }, [actorId, isAdmin, queryClient]);
  return (
    <AdminGuard>
      <AdminNav />
      {children}
    </AdminGuard>
  );
}

function AdminNav() {
  const pathname = usePathname();

  const activeHref = NAV_ITEMS.filter(({ href, exact }) => exact ? pathname === href : pathname === href || pathname.startsWith(href + '/'))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return (
    <div className='sticky top-[72px] z-30 bg-gov-dark/95 backdrop-blur-md border-b border-gov-forest/40 shadow-md'>
      <div className='max-w-[1340px] mx-auto px-5 lg:px-8'>
        <nav aria-label='Admin navigation' className='flex items-center gap-1.5 sm:gap-2 overflow-x-auto py-2.5 scrollbar-hide'>
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = activeHref === href;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? 'page' : undefined}
                onFocus={(event) => event.currentTarget.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })}
                className={`inline-flex min-h-11 items-center gap-2 px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold transition-all whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-gov-gold ${
                  active
                    ? 'bg-gov-gold/20 text-gov-gold ring-1 ring-inset ring-gov-gold/40 shadow-sm'
                    : 'text-white/70 hover:text-white hover:bg-white/10 ring-1 ring-inset ring-transparent'
                }`}>
                <Icon className='w-3.5 h-3.5' />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
