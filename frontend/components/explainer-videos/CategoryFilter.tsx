/**
 * CategoryFilter - Category selection component for filtering videos
 * Displays available categories with icons and handles selection state
 */
'use client';

import { motion } from 'framer-motion';
import { VideoCategory } from '../../data/explainerVideos';

interface CategoryFilterProps {
  categories: VideoCategory[];
  selectedCategory: string;
  onCategorySelect: (categoryId: string) => void;
}

export default function CategoryFilter({
  categories,
  selectedCategory,
  onCategorySelect,
}: CategoryFilterProps) {
  return (
    <div className='mb-8'>
      <h3 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4'>Categories</h3>
      <div className='flex flex-wrap gap-3'>
        {categories.map((category) => {
          const Icon = category.icon;
          return (
            <motion.button
              key={category.id}
              onClick={() => onCategorySelect(category.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl border transition-all duration-200 ${
                selectedCategory === category.id
                  ? 'bg-red-100 border-red-300 text-red-800'
                  : 'bg-white dark:bg-surface-base border-gray-200 dark:border-neutral-border text-gray-700 dark:text-neutral-muted hover:border-red-300'
              }`}
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}>
              <Icon size={16} />
              {category.label}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
