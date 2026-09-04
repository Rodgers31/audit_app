/**
 * WhyThisMatters - Main component explaining the real-world impact of government finance
 * Refactored into modular components for better maintainability
 * Stories data extracted to separate file for easy editing
 */
'use client';

import { Heart } from 'lucide-react';
import ActionSteps from './why-this-matters/ActionSteps';
import ImpactCategories from './why-this-matters/ImpactCategories';

export default function WhyThisMatters() {
  return (
    <div className='bg-white dark:bg-surface-base rounded-3xl p-8 shadow-xl border border-gray-200 dark:border-neutral-border'>
      {/* Page Header */}
      <div className='flex items-center gap-3 mb-8'>
        <Heart size={32} className='text-red-600' />
        <h2 className='text-3xl font-bold text-gray-900 dark:text-neutral-text'>Why This Matters</h2>
      </div>

      {/* Introduction Section */}
      <div className='bg-gradient-to-r from-blue-50 to-red-50 rounded-2xl p-6 mb-8'>
        <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text mb-4'>Your Money, Your Life</h3>
        <p className='text-gray-700 dark:text-neutral-muted leading-relaxed'>
          Government budgets aren't just numbers on paper – they're decisions about your life. Every
          shilling spent (or misspent) affects whether you have good schools, functioning hospitals,
          clean water, and safe roads. When you understand how government finance works, you can
          demand better services and hold leaders accountable.
        </p>
      </div>

      {/* The "Real Stories, Real Impact" grid was withdrawn (credibility audit
          F33). The four narratives carried invented figures — KES 50m of
          medical equipment, KES 80m for a school for 800 children, KES 200m of
          road, KES 300m of youth-employment money "diverted to fund political
          campaigns" — under a heading that said "Real". A composite disclaimer
          above them was not enough on a site whose whole promise is that every
          figure traces to a published document, and the youth-fund story
          attaches a specific sum and a specific motive to a real, named class
          of public fund. The civic guidance below carries no invented data and
          stays. Restore only with stories built from findings this site can
          actually cite. */}

      {/* Impact Categories Section */}
      <ImpactCategories />

      {/* Action Steps Section */}
      <ActionSteps />
    </div>
  );
}
