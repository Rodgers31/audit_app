import type { Metadata } from 'next';
import InteractiveGlossary from '@/components/InteractiveGlossary';

export const metadata: Metadata = {
  title: 'Glossary — AuditGava',
  description: 'Search plain-English definitions of Kenyan budget, spending and audit terms.',
};

export default function GlossaryPage() {
  return (
    <div className='min-h-screen bg-gov-sand dark:bg-surface-sunken'>
      <div className='mx-auto w-full max-w-screen-lg px-4 pb-8 pt-[calc(var(--public-header-height)+1rem)] sm:px-6'>
        <InteractiveGlossary />
      </div>
    </div>
  );
}
