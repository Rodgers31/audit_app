import Footer from '@/components/Footer';
import Navigation from '@/components/Navigation';
import { AuthProvider } from '@/lib/auth/AuthProvider';
import { WatchlistProvider } from '@/lib/auth/WatchlistProvider';
import { LangProvider } from '@/lib/i18n/LangProvider';
import NavTrailTracker from '@/lib/navigation/NavTrailTracker';
import { QueryProvider } from '@/lib/react-query/QueryProvider';
import { Suspense } from 'react';
import { Analytics } from '@vercel/analytics/react';
import { SpeedInsights } from '@vercel/speed-insights/next';
import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'AuditGava — Kenya Public Money Tracker',
    template: '%s | AuditGava',
  },
  description:
    'Where your taxes go — Kenya government financial transparency, updated nightly from official sources',
  keywords: [
    'government',
    'transparency',
    'audit',
    'kenya',
    'budget',
    'spending',
    'national debt',
    'county finances',
  ],
  // www is the canonical production host (the apex 30x-redirects to it).
  // Pointing metadata at the apex made every shared/crawled link pay an
  // extra redirect round-trip before the page could even be requested.
  metadataBase: new URL('https://www.auditgava.com'),
  openGraph: {
    title: 'AuditGava — Kenya Public Money Tracker',
    description:
      "Track Kenya's national debt, county budgets, and government spending — updated nightly from official sources.",
    url: 'https://www.auditgava.com',
    siteName: 'AuditGava',
    images: [
      {
        url: '/og-image.png',
        width: 1536,
        height: 1024,
        alt: 'AuditGava — Kenya Public Money Tracker',
      },
    ],
    locale: 'en_KE',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AuditGava — Kenya Public Money Tracker',
    description:
      "Track Kenya's national debt, county budgets, and government spending — updated nightly from official sources.",
    images: ['/og-image.png'],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Derive API origin once so preconnect/dns-prefetch can warm the TCP + TLS
  // handshake before the first React Query fetch fires on the client.
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
  let apiOrigin = '';
  try {
    if (apiUrl) apiOrigin = new URL(apiUrl).origin;
  } catch {
    // Swallow URL parse errors — falls back to no preconnect.
  }
  return (
    <html lang='en' suppressHydrationWarning>
      <head>
        {/* No-flash dark-mode bootstrap.
            Runs synchronously BEFORE the body paints so the right
            ``dark`` class is on <html> from the very first frame —
            otherwise dark-mode users would see a flash of light
            chrome before React hydrates ThemeToggle and applies the
            class. Reads localStorage["theme"] for an explicit
            choice; otherwise follows ``prefers-color-scheme``.
            Wrapped in try/catch because localStorage can throw in
            private-mode Safari. */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('theme');var sysDark=window.matchMedia('(prefers-color-scheme: dark)').matches;var dark=s==='dark'||(s!=='light'&&sysDark);if(dark)document.documentElement.classList.add('dark');}catch(e){}})();`,
          }}
        />
        {apiOrigin && (
          <>
            <link rel='preconnect' href={apiOrigin} crossOrigin='anonymous' />
            <link rel='dns-prefetch' href={apiOrigin} />
          </>
        )}
        {/* Above-the-fold LCP image — preload so it begins downloading
            in parallel with the CSS / JS chunks. The ``media`` attribute
            ensures only the variant matching the user's current colour
            scheme is downloaded — no double-fetch on dark-mode systems. */}
        <link
          rel='preload'
          as='image'
          href='/kenya_bg_top.jpg'
          media='(prefers-color-scheme: light)'
        />
        <link
          rel='preload'
          as='image'
          href='/kenya_bg_top_dk.jpg'
          media='(prefers-color-scheme: dark)'
        />
      </head>
      <body
        className='bg-gov-sand antialiased'
        suppressHydrationWarning>
        {/* Skip-to-main link. Sighted users never see this (sr-only
            until focused); keyboard users can jump past the fixed
            header in one Tab press. Lands on #main-content which
            PageShell and the home dashboard mark up. */}
        <a
          href='#main-content'
          className='sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:bg-gov-forest focus:text-white focus:px-4 focus:py-2 focus:rounded-lg focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-white'>
          Skip to main content
        </a>
        <QueryProvider>
          <LangProvider>
            <AuthProvider>
              <WatchlistProvider>
                {/* Records every client-side navigation into sessionStorage
                    so "back" links on detail pages can decide whether
                    to pop history (restoring state) or push a fresh URL. */}
                <Suspense fallback={null}>
                  <NavTrailTracker />
                </Suspense>
                <Navigation />
                <div id='main-content' className='relative z-[1]'>
                  {children}
                </div>
                <Footer />
              </WatchlistProvider>
            </AuthProvider>
          </LangProvider>
        </QueryProvider>
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
