import type { Metadata } from 'next';
import type { ReactNode } from 'react';

export const metadata: Metadata = {
  title: { absolute: 'Why public spending figures matter | AuditGava' },
  description: 'Learn what published figures say about spending on health, education and roads, where the figures come from and what they leave out.',
};

export default function WhyItMattersLayout({ children }: { children: ReactNode }) {
  return children;
}
