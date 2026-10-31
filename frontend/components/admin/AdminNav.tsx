"use client";

import {useEffect,useState} from 'react';
import {Activity,BarChart3,History,ListChecks,PlayCircle,Send,Users} from 'lucide-react';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import ThemeToggle from '@/components/ThemeToggle';
import styles from './admin.module.css';

const NAV_ITEMS = [
  { href: '/admin', label: 'Overview', icon: BarChart3, exact: true },
  { href: '/admin/social', label: 'Social', icon: Send },
  { href: '/admin/ingestion', label: 'Data updates', icon: ListChecks },
  { href: '/admin/etl', label: 'Run & recover', icon: PlayCircle },
  { href: '/admin/users', label: 'People', icon: Users },
  { href: '/admin/audit-log', label: 'Activity', icon: History },
  { href: '/status', label: 'System status', icon: Activity },
];

export default function AdminNav() {
  const pathname = usePathname() ?? '';
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => setMenuOpen(false), [pathname]);

  const activeHref = NAV_ITEMS.filter(({ href, exact }) => exact ? pathname === href : pathname === href || pathname.startsWith(href + '/'))
    .sort((a, b) => b.href.length - a.href.length)[0]?.href;

  return <>
    <div className={styles.nav}><div className={styles.navInner}>
      <Link href='/' className={styles.identity} aria-label='AuditGava / Admin — public site'>AuditGava / Admin</Link>
      <button type='button' className={styles.menuButton} aria-controls='admin-task-navigation' aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>Menu</button>
      <nav id='admin-task-navigation' aria-label='Admin navigation' className={`${styles.links} ${menuOpen ? styles.navExpanded : ''}`}>
        {NAV_ITEMS.map(({ href, label, icon: Icon }) => <Link key={href} href={href} aria-current={activeHref === href ? 'page' : undefined}><Icon aria-hidden='true' />{label}</Link>)}
      </nav>
      <div className={styles.utilities}>
        <Link href='/account'>Account</Link>
        <ThemeToggle />
      </div>
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
