import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: 'Unaccounted funds',
  description: 'Read findings the Office of the Auditor-General describes as unaccounted for or a loss of funds, with links to the original reports.',
};

export default function UnaccountedFundsLayout({ children }: { children: ReactNode }) {
  return children;
}
