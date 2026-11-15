import localFont from 'next/font/local';

export const publicSans = localFont({
  src: [
    { path: './fonts/public-sans-400-700.woff2', weight: '400 700', style: 'normal' },
    { path: './fonts/public-sans-400-italic.woff2', weight: '400', style: 'italic' },
  ],
  variable: '--font-audit-sans',
  display: 'swap',
});

export const barlowCondensed = localFont({
  src: [
    { path: './fonts/barlow-condensed-500.woff2', weight: '500' },
    { path: './fonts/barlow-condensed-600.woff2', weight: '600' },
    { path: './fonts/barlow-condensed-700.woff2', weight: '700' },
  ],
  variable: '--font-audit-display',
  display: 'swap',
});

export const ibmPlexMono = localFont({
  src: [
    { path: './fonts/ibm-plex-mono-400.woff2', weight: '400' },
    { path: './fonts/ibm-plex-mono-500.woff2', weight: '500' },
    { path: './fonts/ibm-plex-mono-600.woff2', weight: '600' },
  ],
  variable: '--font-audit-mono',
  display: 'swap',
  preload: false,
});
