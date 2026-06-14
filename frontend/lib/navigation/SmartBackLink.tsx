/**
 * Back-link that prefers history.back() over a fresh push when the
 * user's previous page matches the link target.
 *
 * Why: a plain `<Link href="/counties">` always pushes a fresh URL,
 * discarding the query string (`?p=2`) and scroll position of the
 * previous list view. `router.back()` pops the browser history so
 * the exact previous state is restored — but only when the history
 * stack actually contains the expected prior URL.
 *
 * Decision rule (see `shouldUseBackNavigation` in `./trail.ts`):
 *   - history depth >= 2
 *   - previous trail entry's pathname matches `href`'s pathname
 *   - both checks gated on the tracker having recorded the prior nav
 *
 * If any check fails we fall through to the Link's default push
 * behaviour, so deep-linked visitors still get a working "back" link.
 */
'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import React from 'react';
import { shouldUseBackNavigation } from './trail';

interface SmartBackLinkProps {
  href: string;
  children: React.ReactNode;
  className?: string;
  onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void;
}

export default function SmartBackLink({
  href,
  children,
  className,
  onClick,
}: SmartBackLinkProps) {
  const router = useRouter();

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>): void => {
    onClick?.(e);
    if (e.defaultPrevented) return;
    if (shouldUseBackNavigation(href)) {
      e.preventDefault();
      router.back();
    }
  };

  return (
    <Link href={href} onClick={handleClick} className={className}>
      {children}
    </Link>
  );
}
