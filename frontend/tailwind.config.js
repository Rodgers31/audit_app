/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  // Class strategy: ``dark:`` variants activate when ``<html>``
  // carries the ``dark`` class. The boot script in app/layout.tsx
  // sets that class on first paint based on either an explicit
  // user choice (localStorage ``theme = 'dark'`` / ``'light'``)
  // or — when no choice has been made — the OS
  // ``prefers-color-scheme`` setting. ThemeToggle in the top nav
  // lets the user override OS at any time.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        /* ── Government editorial palette ── */
        gov: {
          dark: '#0F1A12',
          forest: '#1B3A2A',
          sage: '#4A7C5C',
          gold: '#D9A441',
          sand: '#F5F0E8',
          cream: '#FAF7F0',
          copper: '#C94A4A',
          warning: '#D97706',
        },
        neutral: {
          // Theme-aware via CSS variables defined in globals.css.
          // Tailwind v3.3+ syntax: ``rgb(... / <alpha-value>)`` lets
          // us keep using ``text-neutral-text/60`` etc. and have the
          // resolved value crossfade with prefers-color-scheme.
          text: 'rgb(var(--c-neutral-text) / <alpha-value>)',
          muted: 'rgb(var(--c-neutral-muted) / <alpha-value>)',
          border: 'rgb(var(--c-neutral-border) / <alpha-value>)',
          // Hex literals retained for any rare consumer that
          // imports the colour as a JS value rather than via a
          // Tailwind class.
          100: '#F4F2EE',
        },
        // Surface tokens that switch between light + dark via the
        // CSS vars in globals.css. In light mode all three are
        // white-ish so cards look like the existing ``bg-white``;
        // in dark mode they fan out into a layered slate-warm
        // hierarchy (base → elevated → sunken) that gives proper
        // depth instead of the flat green-on-green look.
        surface: {
          base: 'rgb(var(--c-surface-base) / <alpha-value>)',
          elevated: 'rgb(var(--c-surface-elevated) / <alpha-value>)',
          sunken: 'rgb(var(--c-surface-sunken) / <alpha-value>)',
        },
        primary: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          900: '#0c4a6e',
        },
        secondary: {
          50: '#f8fafc',
          100: '#f1f5f9',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          900: '#0f172a',
        },
        success: { 50: '#f0fdf4', 100: '#dcfce7', 500: '#22c55e', 600: '#16a34a', 700: '#15803d' },
        warning: { 50: '#fffbeb', 100: '#fef3c7', 500: '#f59e0b', 600: '#d97706', 700: '#b45309' },
        danger: { 50: '#fef2f2', 100: '#fee2e2', 500: '#ef4444', 600: '#dc2626', 700: '#b91c1c' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        display: ['"DM Serif Display"', 'Georgia', 'serif'],
        mono: ['Fira Code', 'monospace'],
      },
      maxWidth: {
        dashboard: '1400px',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-in-out',
        'slide-up': 'slideUp 0.6s cubic-bezier(0.22,1,0.36,1)',
        'pulse-slow': 'pulse 3s infinite',
        draw: 'draw 1.2s ease-out forwards',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(24px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        draw: {
          '0%': { strokeDashoffset: '1000' },
          '100%': { strokeDashoffset: '0' },
        },
      },
      boxShadow: {
        surface: '0 2px 20px rgba(15,26,18,0.06)',
        elevated: '0 8px 40px rgba(15,26,18,0.10)',
        deep: '0 16px 64px rgba(15,26,18,0.14)',
      },
      backdropBlur: {
        xs: '2px',
      },
    },
  },
  plugins: [require('@tailwindcss/typography')],
};
