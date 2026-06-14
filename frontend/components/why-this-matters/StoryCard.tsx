/**
 * StoryCard - Individual story card component with expandable details
 * Displays real-life stories showing government finance impact
 */
'use client';

import { motion } from 'framer-motion';
import { AlertTriangle, ArrowRight } from 'lucide-react';
import { RealLifeStory } from '../../data/realLifeStories';

interface StoryCardProps {
  story: RealLifeStory;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}

export default function StoryCard({ story, index, isExpanded, onToggle }: StoryCardProps) {
  const Icon = story.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.5 }}
      className='bg-white dark:bg-surface-base rounded-2xl border border-gray-200 dark:border-neutral-border p-6 hover:shadow-lg transition-all duration-300'>
      {/* Story Header */}
      <div className='flex items-start gap-4 mb-4'>
        <div
          className={`w-12 h-12 rounded-xl bg-${story.color}-100 flex items-center justify-center flex-shrink-0`}>
          <Icon size={24} className={`text-${story.color}-600`} />
        </div>
        <div className='flex-1'>
          <h4 className='text-lg font-bold text-gray-900 dark:text-neutral-text mb-1'>{story.title}</h4>
          <p className='text-sm text-gray-600 dark:text-neutral-muted mb-3'>{story.summary}</p>

          {/* Story Metadata */}
          <div className='flex items-center gap-4 text-xs text-gray-500 dark:text-neutral-muted/80 mb-4'>
            <span
              className={`px-2 py-1 rounded-lg ${
                story.impact === 'High'
                  ? 'bg-red-100 text-red-800'
                  : story.impact === 'Medium'
                  ? 'bg-orange-100 text-orange-800'
                  : 'bg-yellow-100 text-yellow-800'
              }`}>
              {story.impact} Impact
            </span>
            <span>📖 {story.timeToRead}</span>
            <span className='capitalize'>{story.category}</span>
          </div>
        </div>
      </div>

      {/* Expand/Collapse Button */}
      <motion.button
        onClick={onToggle}
        className='w-full text-left p-3 rounded-xl bg-gray-50 dark:bg-surface-elevated hover:bg-gray-100 dark:hover:bg-surface-base transition-colors duration-200'
        whileHover={{ scale: 1.02 }}
        whileTap={{ scale: 0.98 }}>
        <div className='flex items-center justify-between'>
          <span className='font-medium text-gray-900 dark:text-neutral-text'>Read Full Story</span>
          <ArrowRight
            size={16}
            className={`text-gray-600 dark:text-neutral-muted transition-transform duration-200 ${
              isExpanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </motion.button>

      {/* Expanded Story Content */}
      {isExpanded && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.3 }}
          className='mt-4 pt-4 border-t border-gray-200 dark:border-neutral-border'>
          <div className='space-y-4 text-sm'>
            {/* What Happened */}
            <div>
              <h5 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>What Happened:</h5>
              <p className='text-gray-700 dark:text-neutral-muted'>{story.story}</p>
            </div>

            {/* Real Consequences */}
            <div>
              <h5 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>Real Consequences:</h5>
              <ul className='space-y-1'>
                {story.consequences.map((consequence, i) => (
                  <li key={i} className='flex items-start gap-2 text-gray-700 dark:text-neutral-muted'>
                    <AlertTriangle size={14} className='text-red-500 mt-0.5 flex-shrink-0' />
                    <span>{consequence}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* What Changed */}
            <div>
              <h5 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>What Changed:</h5>
              <p className='text-gray-700 dark:text-neutral-muted'>{story.whatChanged}</p>
            </div>

            {/* Your Role */}
            <div>
              <h5 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>Your Role:</h5>
              <p className='text-gray-700 dark:text-neutral-muted'>{story.yourRole}</p>
            </div>

            {/* Personal Connection */}
            <div className='bg-blue-50 rounded-xl p-4'>
              <h5 className='font-semibold text-blue-900 mb-2'>Personal Connection:</h5>
              <p className='text-blue-800'>{story.personalConnection}</p>
            </div>
          </div>
        </motion.div>
      )}
    </motion.div>
  );
}
