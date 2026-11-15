'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import type { TranslationKey } from '@/lib/i18n/messages';
import { Menu, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import AuthModal from './AuthModal';
import LangSwitcher from './LangSwitcher';
import ThemeToggle from './ThemeToggle';

type NavItem = { href: string; name: TranslationKey; hint: TranslationKey; short?: TranslationKey };

const GROUPS: { label: TranslationKey; items: NavItem[] }[] = [
  { label: 'shell.explore', items: [
    { href: '/debt', name: 'shell.debt', hint: 'shell.debt_hint' },
    { href: '/budget', name: 'shell.budget_full', short: 'shell.budget', hint: 'shell.budget_hint' },
    { href: '/counties', name: 'shell.counties', hint: 'shell.counties_hint' },
    { href: '/transparency', name: 'shell.transparency', hint: 'shell.transparency_hint' },
    { href: '/audits', name: 'shell.audits', short: 'shell.audits_short', hint: 'shell.audits_hint' },
  ] },
  { label: 'shell.understand', items: [
    { href: '/learn', name: 'shell.learn_full', short: 'shell.learn', hint: 'shell.learn_hint' },
    { href: '/learn/glossary', name: 'shell.glossary', hint: 'shell.glossary_hint' },
  ] },
  { label: 'shell.about_data', items: [
    { href: '/sources', name: 'shell.sources', hint: 'shell.sources_hint' },
    { href: '/about', name: 'shell.about', hint: 'shell.about_hint' },
  ] },
];
const PRIMARY = [...GROUPS[0].items, GROUPS[1].items[0]];
const subscribeToHydration = () => () => {};
const hydratedSnapshot = () => true;
const serverSnapshot = () => false;

const ACCOUNT_LINKS = [
  { href: '/account', name: 'shell.account_settings' },
  { href: '/account?tab=watchlist', name: 'shell.watchlist' },
  { href: '/account?tab=alerts', name: 'shell.alerts' },
] as const;

function KiswahiliOffer() {
  const { ready, setLang, t } = useLang();
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (!ready || !navigator.languages.some(language => /^sw(?:-|$)/i.test(language))) return;
    try {
      setVisible(!localStorage.getItem('auditgava-lang') && !localStorage.getItem('auditgava-sw-offer'));
    } catch {
      setVisible(true);
    }
  }, [ready]);
  if (!visible) return null;

  const choose = (language: 'en' | 'sw') => {
    setLang(language);
    setVisible(false);
    try { localStorage.setItem('auditgava-sw-offer', '1'); } catch { /* Choice remains in memory. */ }
  };

  return (
    <aside lang='sw' className='fixed inset-x-0 top-16 z-40 border-b border-neutral-border bg-surface-base px-4 py-3'>
      <div className='mx-auto flex max-w-screen-xl flex-wrap items-center gap-2 text-sm'>
        <p className='grow font-semibold'>{t('shell.sw_offer')}</p>
        <button type='button' className='audit-control' onClick={() => choose('sw')}>{t('shell.use_sw')}</button>
        <button type='button' className='audit-control' onClick={() => choose('en')}>{t('shell.keep_english')}</button>
      </div>
    </aside>
  );
}

export default function Navigation() {
  const pathname = usePathname() ?? '';
  const privateShell = ['/admin', '/status'].some(route => pathname === route || pathname.startsWith(`${route}/`));
  return privateShell ? null : <PublicNavigation pathname={pathname} />;
}

function PublicNavigation({ pathname }: { pathname: string }) {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const hydrated = useSyncExternalStore(subscribeToHydration, hydratedSnapshot, serverSnapshot);
  const { t } = useLang();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const mobileToggle = useRef<HTMLButtonElement>(null);
  const mobilePanel = useRef<HTMLDivElement>(null);
  const account = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const openAuth = () => { setMobileOpen(false); setAuthOpen(true); };
    window.addEventListener('open-auth-modal', openAuth);
    return () => window.removeEventListener('open-auth-modal', openAuth);
  }, []);

  useEffect(() => {
    setMobileOpen(false);
    if (account.current) account.current.open = false;
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) return;
    const controls = () => Array.from(mobilePanel.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input[type="radio"]:checked',
    ) ?? []);
    controls()[0]?.focus();
    const bodyOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const keys = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileOpen(false);
      if (event.key !== 'Tab') return;
      const focusable = controls();
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    const desktop = window.matchMedia?.('(min-width: 1024px)');
    const resize = () => { if (desktop?.matches) setMobileOpen(false); };
    desktop?.addEventListener('change', resize);
    document.addEventListener('keydown', keys);

    return () => {
      document.body.style.overflow = bodyOverflow;
      document.removeEventListener('keydown', keys);
      desktop?.removeEventListener('change', resize);
      mobileToggle.current?.focus();
    };
  }, [mobileOpen]);

  const active = (href: string) => pathname === href || pathname.startsWith(`${href}/`);
  function signIn() { setMobileOpen(false); setAuthOpen(true); }
  function signOut() {
    logout();
    if (account.current) account.current.open = false;
    setMobileOpen(false);
  }

  return (
    <>
      <header className='fixed inset-x-0 top-0 z-50 isolate border-b border-neutral-border bg-surface-base'>
        <div className='mx-auto flex h-16 max-w-screen-xl items-stretch justify-between gap-2 px-4 sm:px-6'>
          <Link href='/' className='flex shrink-0 items-center gap-2'>
            <span aria-hidden='true' className='grid h-9 w-9 shrink-0 place-items-center rounded border-l-[3px] border-gov-copper bg-gov-dark font-display text-xl font-semibold text-white'>AG</span>
            <span className='leading-none'>
              <span className='block font-display text-[22px] font-semibold uppercase'>AuditGava</span>
              <span aria-hidden='true' className='mt-1 hidden text-xs text-neutral-muted sm:block'>{t('shell.brand_line')}</span>
            </span>
          </Link>
          <nav aria-label={t('shell.primary_nav')} className='hidden min-w-0 items-stretch justify-center gap-0.5 lg:flex xl:gap-2'>
            {PRIMARY.map(({ href, name, short }) => (
              <Link key={href} href={href} aria-current={active(href) ? 'page' : undefined}
                className={`grid min-h-11 place-items-center border-b-2 px-2 text-center text-audit-label font-semibold hover:bg-surface-sunken ${active(href) ? 'border-gov-sage' : 'border-transparent'}`}>
                {t(short ?? name)}
              </Link>
            ))}
          </nav>
          <div className='hidden shrink-0 items-center gap-2 lg:flex'>
            <details className='group relative' onKeyDown={event => {
              if (event.key === 'Escape') {
                event.currentTarget.open = false;
                event.currentTarget.querySelector('summary')?.focus();
              }
            }}>
              <summary className='audit-control cursor-pointer list-none px-2'>{t('lang.label')}</summary>
              <div className='audit-panel absolute right-0 top-full mt-1 w-max max-w-[calc(100vw-2rem)] p-3 shadow-elevated'><LangSwitcher /></div>
            </details>
            <ThemeToggle />
            {!isLoading && (isAuthenticated && user ? (
              <details ref={account} className='relative' onBlur={event => {
                if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
              }} onKeyDown={event => {
                if (event.key === 'Escape') {
                  event.currentTarget.open = false;
                  event.currentTarget.querySelector('summary')?.focus();
                }
              }}>
                <summary aria-label={t('shell.account')} className='audit-control min-w-11 cursor-pointer list-none px-1'>
                  {(user.display_name || user.email || '?').charAt(0).toUpperCase()}
                </summary>
                <div className='audit-panel absolute right-0 top-full mt-1 w-60 p-3 text-sm shadow-elevated'>
                  <p className='truncate font-semibold'>{user.display_name || t('shell.citizen')}</p>
                  <p className='truncate text-neutral-muted'>{user.email}</p>
                  {ACCOUNT_LINKS.map(({ href, name }) => <Link className='audit-receipt flex' href={href} key={href}>{t(name)}</Link>)}
                  <button type='button' className='audit-control' onClick={signOut}>{t('shell.sign_out')}</button>
                </div>
              </details>
            ) : <button type='button' className='audit-control px-2' onClick={signIn}>{t('shell.sign_in')}</button>)}
          </div>
          <button ref={mobileToggle} type='button' className='audit-control self-center lg:hidden'
            disabled={!hydrated} onClick={() => setMobileOpen(open => !open)} aria-expanded={mobileOpen}
            aria-controls={mobileOpen ? 'auditgava-mobile-menu' : undefined} aria-label={t(mobileOpen ? 'shell.close_menu' : 'shell.open_menu')}>
            <Menu size={19} aria-hidden='true' /> {t('shell.menu')}
          </button>
        </div>
      </header>
      <KiswahiliOffer />

      {mobileOpen && (
        <div className='fixed inset-0 z-[60] bg-gov-dark/55 lg:hidden' onMouseDown={event => {
          if (event.target === event.currentTarget) setMobileOpen(false);
        }}>
          <div ref={mobilePanel} id='auditgava-mobile-menu' role='dialog' aria-modal='true' aria-label={t('shell.mobile_nav')}
            className='ml-auto flex h-full w-[min(100%,25rem)] flex-col overflow-y-auto overscroll-contain scroll-pt-16 border-l border-neutral-border bg-surface-base px-4 pb-5'>
            <div className='sticky top-0 z-10 flex min-h-16 items-center justify-between border-b border-neutral-border bg-surface-base'>
              <span className='text-base font-semibold'>{t('shell.menu')}</span>
              <button type='button' className='audit-control min-w-11 px-0' aria-label={t('shell.close_menu')} onClick={() => setMobileOpen(false)}><X size={20} aria-hidden='true' /></button>
            </div>
            <nav aria-label={t('shell.mobile_nav')}>
              {GROUPS.map(({ label, items }) => (
                <div className='my-4' key={label}>
                  <h2 className='border-b border-neutral-border pb-2 text-sm font-semibold text-neutral-muted'>{t(label)}</h2>
                  {items.map(({ href, name, hint }) => (
                    <Link key={href} href={href} aria-current={active(href) ? 'page' : undefined}
                      onClick={() => setMobileOpen(false)}
                      className='block min-h-14 border-b border-neutral-border py-2 hover:bg-surface-sunken'>
                      <span className='block text-base font-semibold'>{t(name)}</span>
                      <span className='block text-sm text-neutral-muted'>{t(hint)}</span>
                    </Link>
                  ))}
                </div>
              ))}
            </nav>
            <LangSwitcher />
            <div className='my-3'><ThemeToggle /></div>
            {!isLoading && (isAuthenticated ? (
              <div className='flex flex-wrap gap-2 border-t border-neutral-border pt-3'>
                <Link href='/account' className='audit-control' onClick={() => setMobileOpen(false)}>{t('shell.account')}</Link>
                <button type='button' className='audit-control' onClick={signOut}>{t('shell.sign_out')}</button>
              </div>
            ) : <button type='button' className='audit-control self-start' onClick={signIn}>{t('shell.sign_in')}</button>)}
          </div>
        </div>
      )}
      <AuthModal isOpen={authOpen} onClose={() => setAuthOpen(false)} />
    </>
  );
}
