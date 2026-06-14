/**
 * Small, crisp Kenya flag badge (circular) — a consistent, on-brand stand-in
 * for the 🇰🇪 emoji, which renders inconsistently across platforms (and as
 * bare "KE" on some). Black / red / green bands with white fimbriations and a
 * simplified central shield.
 */
export function KenyaFlag({ className = 'w-5 h-5' }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      role="img"
      aria-label="Kenya"
      suppressHydrationWarning>
      <defs>
        <clipPath id="kenya-flag-clip">
          <circle cx="12" cy="12" r="12" />
        </clipPath>
      </defs>
      <g clipPath="url(#kenya-flag-clip)">
        <rect width="24" height="24" fill="#ffffff" />
        <rect width="24" height="7" y="0" fill="#000000" />
        <rect width="24" height="7" y="8.5" fill="#BB0000" />
        <rect width="24" height="7" y="17" fill="#006600" />
        {/* simplified central Maasai shield + spears */}
        <rect x="11.45" y="4" width="1.1" height="16" fill="#000000" />
        <ellipse
          cx="12"
          cy="12"
          rx="2.1"
          ry="4.6"
          fill="#BB0000"
          stroke="#ffffff"
          strokeWidth="0.7"
        />
        <rect x="11.6" y="9.5" width="0.8" height="5" fill="#ffffff" />
      </g>
    </svg>
  );
}
