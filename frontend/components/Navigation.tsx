'use client';

import { useAuth } from '@/lib/auth/AuthProvider';
import { AnimatePresence, motion } from 'framer-motion';
import { Bell, Bookmark, Grid, LogIn, LogOut, Menu, Settings, X } from 'lucide-react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import AuthModal from './AuthModal';

export default function Navigation() {
  const pathname = usePathname();
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // Handle scroll effect for glassmorphism intensity
  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  // Close user menu on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    if (userMenuOpen) document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [userMenuOpen]);

  // Listen for global "open-auth-modal" events (dispatched by WatchButton etc.)
  useEffect(() => {
    const openModal = () => setAuthModalOpen(true);
    window.addEventListener('open-auth-modal', openModal);
    return () => window.removeEventListener('open-auth-modal', openModal);
  }, []);

  const navItems = [
    { href: '/', label: 'Dashboard' },
    { href: '/debt', label: 'National Debt' },
    { href: '/budget', label: 'Budget & Spending' },
    { href: '/counties', label: 'County Explorer' },
    { href: '/transparency', label: 'Follow the Money' },
    { href: '/learn', label: 'Learn' },
  ];

  return (
    <>
      <motion.header
        initial={{ y: -100 }}
        animate={{ y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-500 ${
          scrolled
            ? 'bg-gov-dark/95 backdrop-blur-xl shadow-[0_1px_12px_rgba(0,0,0,0.25)] py-3'
            : 'bg-transparent py-6'
        }`}>
        <div className='max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-between'>
          {/* Left: Brand */}
          <Link href='/' className='flex items-center space-x-3 group relative z-50'>
            <div className='w-10 h-10 rounded-full bg-white/10 flex items-center justify-center border border-white/20 backdrop-blur-sm group-hover:bg-white/20 transition-colors relative overflow-hidden shadow-lg'>
              <span className='text-xl relative z-10' suppressHydrationWarning>
                🇰🇪
              </span>
              {/* Shine effect */}
              <div className='absolute inset-0 bg-gradient-to-tr from-transparent via-white/20 to-transparent translate-y-full group-hover:translate-y-0 transition-transform duration-500' />
            </div>
            <span className='text-white font-bold tracking-tight text-lg drop-shadow-md hidden sm:block'>
              Kenya Public Money
            </span>
          </Link>

          {/* Center: Desktop Navigation */}
          <nav className='hidden md:flex items-center space-x-1 bg-white/5 backdrop-blur-md px-2 py-1.5 rounded-full border border-white/10 shadow-lg'>
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`relative px-5 py-2 rounded-full text-sm font-medium transition-all duration-300 ${
                    isActive ? 'text-gov-dark' : 'text-white/80 hover:text-white hover:bg-white/10'
                  }`}>
                  {isActive && (
                    <motion.div
                      layoutId='nav-pill'
                      className='absolute inset-0 bg-gov-sage shadow-sm rounded-full'
                      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                    />
                  )}
                  <span className='relative z-10'>{item.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Right: Auth / Profile & Menu */}
          <div className='flex items-center space-x-3 md:space-x-4 relative z-50'>
            <button className='p-2 rounded-full bg-white/5 hover:bg-white/10 text-white/80 hover:text-white transition-colors border border-white/10 backdrop-blur-sm hidden sm:flex items-center justify-center group'>
              <Grid className='w-5 h-5 group-hover:rotate-90 transition-transform duration-300' />
            </button>

            {/* Auth-aware user button */}
            {isLoading ? (
              <div className='w-10 h-10 rounded-full bg-white/10 animate-pulse' />
            ) : isAuthenticated && user ? (
              <div className='relative' ref={userMenuRef}>
                <button
                  onClick={() => setUserMenuOpen(!userMenuOpen)}
                  aria-haspopup='true'
                  aria-expanded={userMenuOpen}
                  aria-label='User menu'
                  className='w-10 h-10 rounded-full bg-gradient-to-br from-gov-sage to-gov-forest border-2 border-white/20 flex items-center justify-center shadow-lg overflow-hidden relative transition-transform hover:scale-105 active:scale-95'>
                  <span className='text-white font-bold text-sm'>
                    {(user.display_name || user.email)[0].toUpperCase()}
                  </span>
                </button>
                {/* green active dot */}
                <div className='absolute bottom-0 right-0 w-3 h-3 bg-green-400 rounded-full border-2 border-gov-dark' />

                {/* Dropdown */}
                <AnimatePresence>
                  {userMenuOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.95 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.95 }}
                      transition={{ duration: 0.15 }}
                      className='absolute right-0 top-14 w-64 bg-gov-dark/95 backdrop-blur-xl border border-white/15 rounded-2xl shadow-2xl overflow-hidden'
                      role='menu'
                      aria-label='User menu'>
                      {/* User info */}
                      <div className='p-4 border-b border-white/10'>
                        <p className='text-white font-semibold text-sm truncate'>
                          {user.display_name || 'Citizen'}
                        </p>
                        <p className='text-white/50 text-xs truncate'>{user.email}</p>
                      </div>
                      {/* Links */}
                      <div className='py-1'>
                        <Link
                          href='/account'
                          onClick={() => setUserMenuOpen(false)}
                          className='flex items-center gap-3 px-4 py-2.5 text-sm text-white/80 hover:text-white hover:bg-white/10 transition-colors'>
                          <Settings className='w-4 h-4' />
                          Account & Settings
                        </Link>
                        <Link
                          href='/account?tab=watchlist'
                          onClick={() => setUserMenuOpen(false)}
                          className='flex items-center gap-3 px-4 py-2.5 text-sm text-white/80 hover:text-white hover:bg-white/10 transition-colors'>
                          <Bookmark className='w-4 h-4' />
                          My Watchlist
                        </Link>
                        <Link
                          href='/account?tab=alerts'
                          onClick={() => setUserMenuOpen(false)}
                          className='flex items-center gap-3 px-4 py-2.5 text-sm text-white/80 hover:text-white hover:bg-white/10 transition-colors'>
                          <Bell className='w-4 h-4' />
                          Alerts
                        </Link>
                      </div>
                      {/* Logout */}
                      <div className='p-2 border-t border-white/10'>
                        <button
                          onClick={() => {
                            logout();
                            setUserMenuOpen(false);
                          }}
                          className='flex items-center gap-3 w-full px-3 py-2.5 text-sm text-gov-copper hover:bg-gov-copper/10 rounded-xl transition-colors'>
                          <LogOut className='w-4 h-4' />
                          Sign Out
                        </button>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            ) : (
              <button
                onClick={() => setAuthModalOpen(true)}
                className='flex items-center gap-2 px-4 py-2 rounded-full bg-gov-sage/80 hover:bg-gov-sage text-white text-sm font-medium transition-all border border-gov-sage/40 shadow-md hover:shadow-lg active:scale-95'>
                <LogIn className='w-4 h-4' />
                <span className='hidden sm:inline'>Sign In</span>
              </button>
            )}

            <button
              className='md:hidden p-2 text-white/90 hover:text-white bg-white/10 rounded-full backdrop-blur-md'
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-expanded={mobileMenuOpen}
              aria-controls='mobile-menu'
              aria-label={mobileMenuOpen ? 'Close navigation menu' : 'Open navigation menu'}>
              {mobileMenuOpen ? <X className='w-6 h-6' /> : <Menu className='w-6 h-6' />}
            </button>
          </div>
        </div>
      </motion.header>

      {/* Mobile Menu Overlay */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            id='mobile-menu'
            role='navigation'
            aria-label='Mobile navigation'
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            className='fixed inset-0 z-40 pt-24 px-6 md:hidden flex flex-col items-center space-y-8'
            style={{ backgroundColor: '#0F1A12' }}>
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`text-2xl font-bold transition-colors ${
                    isActive ? 'text-gov-gold' : 'text-gov-sage hover:text-gov-gold'
                  }`}
                  onClick={() => setMobileMenuOpen(false)}>
                  {item.label}
                </Link>
              );
            })}
            <div className='w-16 h-1 bg-gov-sage/30 rounded-full mt-8' />

            {/* Mobile auth links */}
            {isAuthenticated ? (
              <>
                <Link
                  href='/account'
                  className='text-lg font-semibold text-gov-gold hover:text-gov-warning transition-colors'
                  onClick={() => setMobileMenuOpen(false)}>
                  My Account
                </Link>
                <button
                  onClick={() => {
                    logout();
                    setMobileMenuOpen(false);
                  }}
                  className='text-lg font-semibold text-gov-copper hover:text-gov-copper/80 transition-colors'>
                  Sign Out
                </button>
              </>
            ) : (
              <button
                onClick={() => {
                  setMobileMenuOpen(false);
                  setAuthModalOpen(true);
                }}
                className='text-lg font-semibold text-gov-gold hover:text-gov-warning transition-colors'>
                Sign In / Register
              </button>
            )}

            <div className='text-gov-sage/60 text-sm font-medium uppercase tracking-widest'>
              Republic of Kenya
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Auth Modal */}
      <AuthModal isOpen={authModalOpen} onClose={() => setAuthModalOpen(false)} />
    </>
  );
}
