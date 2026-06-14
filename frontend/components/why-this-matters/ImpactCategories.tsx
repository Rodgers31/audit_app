/**
 * ImpactCategories - Display how government spending affects different aspects of life
 * Shows personal, community, and economic impacts with concrete examples
 */
'use client';

import { motion } from 'framer-motion';
import { Heart, TrendingUp, Users } from 'lucide-react';

interface ImpactCategory {
  id: string;
  title: string;
  icon: any;
  description: string;
  examples: string[];
}

export default function ImpactCategories() {
  const impactCategories: ImpactCategory[] = [
    {
      id: 'personal',
      title: 'Personal Impact',
      icon: Heart,
      description: 'How government spending affects your daily life',
      examples: [
        "Healthcare: Whether hospitals have medicine when you're sick",
        'Education: Quality of schools your children attend',
        'Roads: Condition of roads you use daily',
        'Water: Reliability of water supply to your home',
        'Security: Police response times in your neighborhood',
      ],
    },
    {
      id: 'community',
      title: 'Community Impact',
      icon: Users,
      description: 'How budgets shape your entire neighborhood',
      examples: [
        'Markets: Infrastructure for local businesses to thrive',
        'Employment: Job creation through government projects',
        'Environment: Waste management and clean air initiatives',
        'Culture: Support for local arts and community centers',
        'Sports: Facilities for youth and community recreation',
      ],
    },
    {
      id: 'economic',
      title: 'Economic Impact',
      icon: TrendingUp,
      description: 'How government finance affects prosperity',
      examples: [
        'Investment: Whether businesses want to operate in your area',
        'Property values: How infrastructure affects land prices',
        'Cost of living: How efficient government services reduce your expenses',
        'Income opportunities: Government projects that create jobs',
        'Future growth: Infrastructure that attracts development',
      ],
    },
  ];

  return (
    <div className='mb-12'>
      <h3 className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-6'>How It Affects You</h3>

      <div className='grid grid-cols-1 md:grid-cols-3 gap-6'>
        {impactCategories.map((category, index) => {
          const Icon = category.icon;
          return (
            <motion.div
              key={category.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.5 }}
              className='bg-gradient-to-br from-gray-50 to-gray-100 rounded-2xl p-6'>
              {/* Category Header */}
              <div className='flex items-center gap-3 mb-4'>
                <div className='w-10 h-10 rounded-xl bg-blue-100 flex items-center justify-center'>
                  <Icon size={20} className='text-blue-600' />
                </div>
                <h4 className='text-lg font-bold text-gray-900 dark:text-neutral-text'>{category.title}</h4>
              </div>

              {/* Category Description */}
              <p className='text-gray-600 dark:text-neutral-muted text-sm mb-4'>{category.description}</p>

              {/* Examples List */}
              <ul className='space-y-2'>
                {category.examples.map((example, i) => (
                  <li key={i} className='flex items-start gap-2 text-sm text-gray-700 dark:text-neutral-muted'>
                    <div className='w-1.5 h-1.5 rounded-full bg-blue-500 mt-2 flex-shrink-0' />
                    <span>{example}</span>
                  </li>
                ))}
              </ul>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
