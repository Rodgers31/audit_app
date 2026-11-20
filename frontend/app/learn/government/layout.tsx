import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: { absolute: 'How Kenya is governed | AuditGava' },
  description: 'Explore Kenya’s executive, legislature and judiciary, and how national and county governments share responsibilities.',
};

export default function GovernmentLayout({ children }: { children: ReactNode }) {
  return children;
}
