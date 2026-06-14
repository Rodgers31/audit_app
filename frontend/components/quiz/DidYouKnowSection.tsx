/**
 * DidYouKnowSection - Displays interesting facts about Kenya's government finances
 * Educational content to engage users between quizzes
 */
'use client';

import { motion } from 'framer-motion';
import { Lightbulb } from 'lucide-react';

interface DidYouKnowFact {
  icon: string;
  fact: string;
  detail: string;
}

interface DidYouKnowSectionProps {
  facts: DidYouKnowFact[];
}

export default function DidYouKnowSection({ facts }: DidYouKnowSectionProps) {
  return (
    <div className='bg-gradient-to-r from-blue-50 to-purple-50 rounded-2xl p-6'>
      <div className='flex items-center gap-3 mb-6'>
        <Lightbulb size={24} className='text-yellow-500' />
        <h3 className='text-xl font-bold text-gray-900 dark:text-neutral-text'>Did You Know?</h3>
      </div>

      <div className='grid grid-cols-1 md:grid-cols-2 gap-4'>
        {facts.slice(0, 4).map((fact, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: index * 0.1, duration: 0.5 }}
            className='bg-white dark:bg-surface-base rounded-xl p-4 border border-gray-100 dark:border-neutral-border'>
            <div className='flex items-start gap-3'>
              <div className='text-2xl'>{fact.icon}</div>
              <div>
                <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-1'>{fact.fact}</h4>
                <p className='text-sm text-gray-600 dark:text-neutral-muted'>{fact.detail}</p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
