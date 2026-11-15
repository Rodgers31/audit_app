import type { Metadata } from 'next';
import MissingPage from '@/components/layout/MissingPage';

export const metadata: Metadata = { title: 'We can’t find that page' };

export default function NotFound() {
  return <MissingPage />;
}
