/**
 * VideosGrid - Grid layout for displaying video cards with filtering
 * Manages video display and handles empty states
 */
'use client';

import { Play } from 'lucide-react';
import { ExplainerVideo } from '../../data/explainerVideos';
import VideoCard from './VideoCard';

interface VideosGridProps {
  videos: ExplainerVideo[];
  onVideoSelect: (videoId: string) => void;
}

export default function VideosGrid({ videos, onVideoSelect }: VideosGridProps) {
  return (
    <>
      {/* Videos Grid */}
      <div className='grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6'>
        {videos.map((video, index) => (
          <VideoCard key={video.id} video={video} index={index} onVideoSelect={onVideoSelect} />
        ))}
      </div>

      {/* No Results */}
      {videos.length === 0 && (
        <div className='text-center py-12'>
          <Play size={48} className='text-gray-300 dark:text-neutral-muted/60 mx-auto mb-4' />
          <h3 className='text-xl font-semibold text-gray-600 dark:text-neutral-muted mb-2'>No videos found</h3>
          <p className='text-gray-500 dark:text-neutral-muted/80'>Try adjusting your search or category filter</p>
        </div>
      )}
    </>
  );
}
