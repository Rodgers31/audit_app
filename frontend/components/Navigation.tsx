'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { useLang } from '@/lib/i18n/LangProvider';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { Bell, Bookmark, LogIn, LogOut, Menu, Settings, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import AuthModal from './AuthModal';
import LangSwitcher from './LangSwitcher';
import ThemeToggle from './ThemeToggle';

function BrandMark() {
  return (
    <span
      aria-hidden='true'
      className='relative grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-sm bg-gov-dark ring-1 ring-gov-dark'>
      <span className='absolute inset-y-0 left-0 w-1 bg-gov-copper' />
      <span className='absolute left-2 right-1.5 top-[11px] h-px bg-gov-cream/75' />
      <span className='absolute left-2 right-1.5 top-[17px] h-px bg-gov-cream/75' />
      <span className='absolute left-2 right-1.5 top-[23px] h-px bg-gov-gold' />
    </span>
  );
}

export default function Navigation() {
  const pathname = usePathname();
  const reduceMotion = useReducedMotion();
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const { t } = useLang();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    if (userMenuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [userMenuOpen]);

  useEffect(() => {
    const openModal = () => setAuthModalOpen(true);
    window.addEventListener('open-auth-modal', openModal);
    return () => window.removeEventListener('open-auth-modal', openModal);
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return;

    const panel = mobileMenuRef.current;
    const getFocusable = () =>
      panel
        ? Array.from(
            panel.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
            ),
          )
        : [];

    const focusTimer = window.setTimeout(() => getFocusable()[0]?.focus(), 0);
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setMobileMenuOpen(false);
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = getFocusable();
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
      mobileToggleRef.current?.focus();
    };
  }, [mobileMenuOpen]);

  useEffect(() => setMobileMenuOpen(false), [pathname]);

  const navItems = [
    { href: '/', label: t('nav.dashboard') },
    { href: '/debt', label: t('nav.debt') },
    { href: '/budget', label: t('nav.budget') },
    { href: '/counties', label: t('nav.counties') },
    { href: '/transparency', label: t('nav.transparency') },
    { href: '/learn', label: t('nav.learn') },
  ];
  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname === href || pathname.startsWith(`${href}/`);

  return (
    <>
      <motion.header
        initial={false}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
        className='ledger-nav-enter fixed inset-x-0 top-0 z-50 isolate border-b border-neutral-border bg-gov-cream/95 dark:bg-gov-dark/95'>
        <div className='mx-auto flex h-16 max-w-[1480px] items-stretch px-4 sm:px-6 lg:px-8'>
          <Link
            href='/'
            aria-label='AuditGava dashboard'
            className='group flex shrink-0 items-center gap-3 border-r border-neutral-border pr-4 sm:pr-6'>
            <BrandMark />
            <span className='hidden sm:block'>
              <span className='block font-display text-[22px] font-semibold uppercase leading-none tracking-[0.02em] text-gov-dark dark:text-white'>
                AuditGava
              </span>
              <span className='mt-1 block font-mono text-[11px] font-medium uppercase tracking-[0.15em] text-neutral-muted'>
                Public money · evidence first
              </span>
            </span>
          </Link>

          <nav aria-label='Primary navigation' className='hidden min-w-0 flex-1 items-stretch xl:flex'>
            {navItems.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? 'page' : undefined}
                  className={`relative flex items-center whitespace-nowrap px-3 text-[12px] font-semibold min-[1440px]:px-4 min-[1440px]:text-[13px] ${
                    active
                      ? 'text-gov-dark dark:text-white'
                      : 'text-neutral-muted hover:bg-surface-sunken/55 hover:text-gov-dark dark:hover:text-white'
                  }`}>
                  {item.label}
                  {active && (
                    <motion.span
                      layoutId='nav-underline'
                      className='absolute inset-x-3 bottom-0 h-[3px] origin-left bg-gov-sage min-[1440px]:inset-x-4'
                      transition={{ duration: reduceMotion ? 0 : 0.2, ease: 'easeOut' }}
                    />
                  )}
                </Link>
              );
            })}
          </nav>

          <div className='ml-auto flex shrink-0 items-center gap-2 border-l border-neutral-border pl-3 sm:pl-4'>
            <div className='hidden xl:block'>
              <LangSwitcher />
            </div>
            <ThemeToggle />

            {isLoading ? (
              <div className='h-9 w-20 animate-pulse rounded-sm bg-surface-sunken' aria-hidden='true' />
            ) : isAuthenticated && user ? (
              <div className='relative' ref={userMenuRef}>
                <button
                  type='button'
                  onClick={() => setUserMenuOpen((open) => !open)}
                  aria-haspopup='menu'
                  aria-expanded={userMenuOpen}
                  aria-label='User menu'
                  className='relative grid h-9 min-w-9 place-items-center rounded-sm border border-gov-sage bg-gov-sage px-2 font-mono text-sm font-semibold text-white hover:bg-gov-forest'>
                  {(user.display_name || user.email)[0].toUpperCase()}
                </button>
                <AnimatePresence>
                  {userMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: 6 }}
                      transition={{ duration: reduceMotion ? 0 : 0.14, ease: 'easeOut' }}
                      className='absolute right-0 top-12 w-64 overflow-hidden rounded-sm border border-neutral-border bg-surface-elevated shadow-elevated'
                      role='menu'
                      aria-label='User menu'>
                      <div className='border-b border-neutral-border p-4'>
                        <p className='truncate text-sm font-semibold text-gov-dark dark:text-white'>
                          {user.display_name || 'Citizen'}
                        </p>
                        <p className='mt-1 truncate font-mono text-[11px] text-neutral-muted'>
                          {user.email}
                        </p>
                      </div>
                      <div className='py-1'>
                        {[
                          { href: '/account', label: 'Account & settings', Icon: Settings },
                          { href: '/account?tab=watchlist', label: 'My watchlist', Icon: Bookmark },
                          { href: '/account?tab=alerts', label: 'Alerts', Icon: Bell },
                        ].map(({ href, label, Icon }) => (
                          <Link
                            key={href}
                            href={href}
                            role='menuitem'
                            onClick={() => setUserMenuOpen(false)}
                            className='flex items-center gap-3 px-4 py-2.5 text-sm text-neutral-muted hover:bg-surface-sunken hover:text-gov-dark dark:hover:text-white'>
                            <Icon className='h-4 w-4' aria-hidden='true' />
                            {label}
                          </Link>
                        ))}
                      </div>
                      <div className='border-t border-neutral-border p-2'>
                        <button
                          type='button'
                          role='menuitem'
                          onClick={() => {
                            logout();
                            setUserMenuOpen(false);
                          }}
                          className='flex w-full items-center gap-3 rounded-[2px] px-3 py-2.5 text-sm font-semibold text-gov-copper hover:bg-gov-copper/10'>
                          <LogOut className='h-4 w-4' aria-hidden='true' />
                          Sign out
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : (
              <button
                type='button'
                onClick={() => setAuthModalOpen(true)}
                className='flex h-9 items-center gap-2 rounded-sm bg-gov-sage px-3 text-sm font-semibold text-white hover:bg-gov-forest active:translate-y-px'>
                <LogIn className='h-4 w-4' aria-hidden='true' />
                <span className='hidden sm:inline'>{t('nav.sign_in')}</span>
              </button>
            )}

            <button
              ref={mobileToggleRef}
              type='button'
              className='tap-44 grid h-9 w-9 place-items-center rounded-sm border border-neutral-border bg-surface-base text-gov-dark hover:border-gov-sage hover:text-gov-sage dark:text-white xl:hidden'
              onClick={() => setMobileMenuOpen((open) => !open)}
              aria-expanded={mobileMenuOpen}
              aria-controls='mobile-menu'
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}>
              {mobileMenuOpen ? <X className='h-5 w-5' /> : <Menu className='h-5 w-5' />}
            </button>
          </div>
        </div>
      </motion.header>

      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            id='mobile-menu'
            role='dialog'
            aria-modal='true'
            aria-label='Mobile navigation'
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduceMotion ? 0 : 0.16 }}
            className='fixed inset-0 z-40 bg-gov-dark/60 pt-16 xl:hidden'
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) setMobileMenuOpen(false);
            }}>
            <motion.div
              ref={mobileMenuRef}
              initial={reduceMotion ? false : { x: 28 }}
              animate={{ x: 0 }}
              exit={{ x: 28 }}
              transition={{ duration: reduceMotion ? 0 : 0.2, ease: 'easeOut' }}
              className='ml-auto flex h-full w-[min(88vw,390px)] flex-col border-l border-neutral-border bg-gov-cream p-6 dark:bg-gov-dark'>
              <p className='source-label mb-5'>Navigate the public record</p>
              <nav aria-label='Mobile primary navigation' className='border-t border-neutral-border'>
                {navItems.map((item, index) => {
                  const active = isActive(item.href);
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      aria-current={active ? 'page' : undefined}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`group flex min-h-14 items-center justify-between border-b border-neutral-border py-3 ${
                        active ? 'text-gov-sage' : 'text-gov-dark dark:text-white'
                      }`}>
                      <span className='font-display text-2xl font-semibold uppercase tracking-[0.02em]'>
                        {item.label}
                      </span>
                      <span className='font-mono text-[11px] text-neutral-muted'>
                        {String(index + 1).padStart(2, '0')}
                      </span>
                    </Link>
                  );
                })}
              </nav>
              <div className='mt-6'>
                <LangSwitcher />
              </div>
              <div className='mt-auto border-t border-neutral-border pt-5'>
                {isAuthenticated ? (
                  <div className='flex gap-3'>
                    <Link href='/account' className='btn-secondary flex-1 text-center' onClick={() => setMobileMenuOpen(false)}>
                      My account
                    </Link>
                    <button
                      type='button'
                      onClick={() => {
                        logout();
                        setMobileMenuOpen(false);
                      }}
                      className='btn border border-gov-copper/35 text-gov-copper'>
                      Sign out
                    </button>
                  </div>
                ) : (
                  <button
                    type='button'
                    onClick={() => {
                      setMobileMenuOpen(false);
                      setAuthModalOpen(true);
                    }}
                    className='btn-primary w-full'>
                    Sign in or register
                  </button>
                )}
                <p className='mt-4 font-mono text-[11px] uppercase tracking-[0.13em] text-neutral-muted'>
                  Republic of Kenya · independent civic technology
                </p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />
    </>
  );
}
