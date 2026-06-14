/**
 * ExplainerVideos - Main component for educational videos about government finance
 * Refactored into modular components for better maintainability
 * Video data extracted to separate file for easy editing
 */
'use client';

import { Play } from 'lucide-react';
import { useState } from 'react';
import { explainerVideos, filterVideos, videoCategories } from '../data/explainerVideos';
import CategoryFilter from './explainer-videos/CategoryFilter';
import VideoModal from './explainer-videos/VideoModal';
import VideosGrid from './explainer-videos/VideosGrid';

interface ExplainerVideosProps {
  searchTerm: string;
}

export default function ExplainerVideos({ searchTerm }: ExplainerVideosProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>('popular');
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);

  // Filter videos based on search term and selected category
  const filteredVideos = filterVideos(explainerVideos, searchTerm, selectedCategory);

  // Get selected video object for modal
  const selectedVideoData = selectedVideo
    ? explainerVideos.find((v) => v.id === selectedVideo) || null
    : null;

  return (
    <div className='bg-white dark:bg-surface-base rounded-3xl p-8 shadow-xl border border-gray-200 dark:border-neutral-border'>
      {/* Page Header */}
      <div className='flex items-center gap-3 mb-8'>
        <Play size={32} className='text-red-600' />
        <h2 className='text-3xl font-bold text-gray-900 dark:text-neutral-text'>Explainer Videos</h2>
      </div>

      {/* Category Filter */}
      <CategoryFilter
        categories={videoCategories}
        selectedCategory={selectedCategory}
        onCategorySelect={setSelectedCategory}
      />

      {/* Videos Grid */}
      <VideosGrid videos={filteredVideos} onVideoSelect={setSelectedVideo} />

      {/* Video Modal */}
      <VideoModal
        video={selectedVideoData}
        isOpen={!!selectedVideo}
        onClose={() => setSelectedVideo(null)}
      />
    </div>
  );
}
