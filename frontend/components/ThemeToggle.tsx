/**
 * ThemeToggle — pill button that toggles between Light ↔ Dark.
 *
 * First-time visitors get the OS preference applied automatically by
 * the no-flash boot script in app/layout.tsx (no localStorage entry
 * yet, so the script falls back to ``prefers-color-scheme``). This
 * button shows the icon for the OPPOSITE state — i.e. if you're in
 * dark mode it shows a sun (click to go light) and vice versa.
 * Clicking always writes an explicit ``light`` or ``dark`` to
 * ``localStorage["theme"]`` so subsequent loads honour the choice.
 *
 * If a viewer never clicks the toggle, the page continues to track
 * their OS preference in real time (``prefers-color-scheme`` change
 * listener).
 */
'use client';

import { Moon, Sun } from 'lucide-react';
import { useEffect, useState } from 'react';

type ResolvedTheme = 'light' | 'dark';
const STORAGE_KEY = 'theme';

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function readStoredOrSystem(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light';
  const v = window.localStorage.getItem(STORAGE_KEY);
  if (v === 'light' || v === 'dark') return v;
  return getSystemTheme();
}

function applyToHtml(theme: ResolvedTheme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
}

export default function ThemeToggle({ className = '' }: { className?: string }) {
  // ``mounted`` keeps SSR/CSR markup in sync — server can't read
  // localStorage / matchMedia, so we render a transparent placeholder
  // until the first effect runs.
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<ResolvedTheme>('light');

  useEffect(() => {
    const initial = readStoredOrSystem();
    setTheme(initial);
    applyToHtml(initial);
    setMounted(true);

    // If the user has not made an explicit choice yet, follow the OS
    // in real time. After they click the button (which writes to
    // localStorage), this listener becomes a no-op.
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (window.localStorage.getItem(STORAGE_KEY) === null) {
        const next = getSystemTheme();
        setTheme(next);
        applyToHtml(next);
      }
    };
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  function toggle() {
    const next: ResolvedTheme = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    applyToHtml(next);
  }

  const baseClass =
    'p-2 rounded-full bg-white/5 hover:bg-white/10 text-white/80 hover:text-white transition-colors border border-white/10 backdrop-blur-sm flex items-center justify-center';

  if (!mounted) {
    return (
      <button
        type='button'
        className={`${baseClass} ${className}`}
        aria-hidden='true'
        tabIndex={-1}>
        <Sun className='w-5 h-5 opacity-0' />
      </button>
    );
  }

  // Show the icon for the OPPOSITE state — what the click will produce.
  // (A common UX pattern: in dark mode you see a sun "switch to light".)
  const isDark = theme === 'dark';
  const Icon = isDark ? Sun : Moon;
  const label = isDark ? 'Switch to light theme' : 'Switch to dark theme';

  return (
    <button
      type='button'
      onClick={toggle}
      title={label}
      aria-label={label}
      className={`${baseClass} ${className}`}>
      <Icon className='w-5 h-5' />
    </button>
  );
}
