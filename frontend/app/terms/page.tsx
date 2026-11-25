import type { Metadata } from 'next';
import { TermsDraft } from './TermsDraft';

export const metadata: Metadata = {
  title: 'Terms of Use draft',
  robots: { index: false, follow: true },
};

export default function TermsPage() {
  return <TermsDraft />;
}
