/**
 * /admin – shared shell for the admin section.
 *
 * Wraps every admin route in <AdminGuard> (third defence layer behind
 * Next.js middleware and backend ``require_admin``) and renders a
 * task navigation and compact private-page headers. Public pages keep
 * their own shell; authorization and actor-scoped cache eviction are shared.
 */
'use client';

import { AdminGuard, useAdmin } from '@/lib/auth/admin';
import { useAuth } from '@/lib/auth/AuthProvider';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
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
import styles from '@/components/admin/admin.module.css';

const NAV_ITEMS = [
  { href: '/admin', label: 'Overview', icon: BarChart3, exact: true },
  { href: '/admin/social', label: 'Social', icon: Send },
  { href: '/admin/ingestion', label: 'Data updates', icon: ListChecks },
  { href: '/admin/etl', label: 'Run & recover', icon: PlayCircle },
  { href: '/admin/users', label: 'People', icon: Users },
  { href: '/admin/audit-log', label: 'Activity', icon: History },
  { href: '/status', label: 'System status', icon: Activity },
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
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const activeHref = NAV_ITEMS.filter(({ href, exact }) => exact ? pathname === href : pathname === href || pathname.startsWith(href + '/'))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return <>
    <div className={styles.nav}><div className={styles.navInner}>
      <span className={styles.identity}>AuditGava / Admin</span>
      <button type='button' className={styles.menuButton} aria-controls='admin-task-navigation' aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>Menu</button>
      <nav id='admin-task-navigation' aria-label='Admin navigation' className={`${styles.links} ${menuOpen ? styles.navExpanded : ''}`}>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={activeHref === href ? 'page' : undefined}><Icon aria-hidden='true' />{label}</Link>)}
      </nav>
    </div></div>
    {pathname.startsWith('/admin/social') && <div className={styles.socialNav}><nav className={styles.socialNavInner} aria-label='Social workspace'>
      <Link href='/admin/social' aria-current={pathname === '/admin/social' ? 'page' : undefined}>Review drafts</Link>
      <Link href='/admin/social/new' aria-current={pathname === '/admin/social/new' ? 'page' : undefined}>Write a post</Link>
      <Link href='/admin/social/studio' aria-current={pathname === '/admin/social/studio' ? 'page' : undefined}>Studio & calendar</Link>
      <details className={styles.settings}><summary>Manage social</summary><div>
        <Link href='/admin/social/automation'>Draft automation</Link><Link href='/admin/social/media'>Media library</Link><Link href='/admin/social/accounts'>Connected accounts</Link><Link href='/admin/social/privacy'>Privacy & retention</Link>
      </div></details>
    </nav></div>}
  </>;
}
