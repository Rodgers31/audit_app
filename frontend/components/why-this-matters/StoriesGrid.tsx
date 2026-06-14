/**
 * StoriesGrid - Grid layout for displaying real-life stories with search functionality
 * Manages story expansion state and filtering
 */
'use client';

import { Heart } from 'lucide-react';
import { useState } from 'react';
import { filterStories, RealLifeStory } from '../../data/realLifeStories';
import StoryCard from './StoryCard';

interface StoriesGridProps {
  stories: RealLifeStory[];
  searchTerm: string;
}

export default function StoriesGrid({ stories, searchTerm }: StoriesGridProps) {
  const [selectedStory, setSelectedStory] = useState<string | null>(null);

  // Filter stories based on search term
  const filteredStories = filterStories(stories, searchTerm);

  const toggleStory = (storyId: string) => {
    setSelectedStory(selectedStory === storyId ? null : storyId);
  };

  return (
    <div className='mb-12'>
      <h3 className='text-2xl font-bold text-gray-900 dark:text-neutral-text mb-6'>Real Stories, Real Impact</h3>

      {/* Stories Grid */}
      <div className='grid grid-cols-1 md:grid-cols-2 gap-6 mb-8'>
        {filteredStories.map((story, index) => (
          <StoryCard
            key={story.id}
            story={story}
            index={index}
            isExpanded={selectedStory === story.id}
            onToggle={() => toggleStory(story.id)}
          />
        ))}
      </div>

      {/* No Results Message */}
      {filteredStories.length === 0 && (
        <div className='text-center py-12'>
          <Heart size={48} className='text-gray-300 dark:text-neutral-muted/60 mx-auto mb-4' />
          <h3 className='text-xl font-semibold text-gray-600 dark:text-neutral-muted mb-2'>No stories found</h3>
          <p className='text-gray-500 dark:text-neutral-muted/80'>Try adjusting your search term</p>
        </div>
      )}
    </div>
  );
}
