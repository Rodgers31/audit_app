"use client";

import SmartBackLink from '@/lib/navigation/SmartBackLink';
import type { ReactNode } from 'react';
import styles from './admin.module.css';

/** Compact task header for private work. Public PageShell keeps its own design. */
export default function AdminPageShell({ title, subtitle, back, children, className = '' }: {
  title: string; subtitle?: string; back?: { href: string; label: string }; children: ReactNode; className?: string;
}) {
  return <div className={styles.page}>
    <header className={styles.heading}>
      {back && <SmartBackLink href={back.href} className={styles.back}>← {back.label}</SmartBackLink>}
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
    <div className={`${styles.content} page-shell-content ${className}`}>{children}</div>
  </div>;
}
