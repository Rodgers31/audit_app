/**
 * VideoCard - Individual video card component with thumbnail, metadata, and play functionality
 * Displays video information and handles user interactions
 */
'use client';

import { motion } from 'framer-motion';
import { Clock, Eye, Play, Star } from 'lucide-react';
import { ExplainerVideo } from '../../data/explainerVideos';
import VideoThumbnail from './VideoThumbnail';

interface VideoCardProps {
  video: ExplainerVideo;
  index: number;
  onVideoSelect: (videoId: string) => void;
}

export default function VideoCard({ video, index, onVideoSelect }: VideoCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.5 }}
      className='bg-white dark:bg-surface-base rounded-2xl border border-gray-200 dark:border-neutral-border overflow-hidden shadow-sm hover:shadow-lg transition-all duration-300'>
      {/* Video Thumbnail */}
      <div className='relative h-48 overflow-hidden'>
        <VideoThumbnail thumbnail={video.thumbnail} />

        {/* Play Button Overlay */}
        <motion.button
          onClick={() => onVideoSelect(video.id)}
          className='absolute inset-0 bg-black/20 flex items-center justify-center opacity-0 hover:opacity-100 transition-opacity duration-200'
          whileHover={{ scale: 1.05 }}
          whileTap={{ scale: 0.95 }}>
          <div className='w-16 h-16 bg-white dark:bg-surface-base rounded-full flex items-center justify-center shadow-lg'>
            <Play size={24} className='text-gray-800 dark:text-neutral-text ml-1' />
          </div>
        </motion.button>

        {/* Duration Badge */}
        <div className='absolute top-3 right-3 bg-black/70 text-white px-2 py-1 rounded-lg text-sm font-medium'>
          {video.duration}
        </div>

        {/* Difficulty Badge */}
        <div
          className={`absolute top-3 left-3 px-2 py-1 rounded-lg text-xs font-medium ${
            video.difficulty === 'beginner'
              ? 'bg-green-100 text-green-800'
              : video.difficulty === 'intermediate'
              ? 'bg-orange-100 text-orange-800'
              : 'bg-red-100 text-red-800'
          }`}>
          {video.difficulty}
        </div>
      </div>

      {/* Video Info */}
      <div className='p-6'>
        <h3 className='text-lg font-bold text-gray-900 dark:text-neutral-text mb-2 line-clamp-2'>{video.title}</h3>

        <p className='text-gray-600 dark:text-neutral-muted text-sm mb-4 line-clamp-2'>{video.description}</p>

        {/* Topics */}
        <div className='flex flex-wrap gap-2 mb-4'>
          {video.topics.slice(0, 2).map((topic) => (
            <span key={topic} className='bg-gray-100 dark:bg-surface-elevated text-gray-700 dark:text-neutral-muted px-2 py-1 rounded-lg text-xs'>
              {topic}
            </span>
          ))}
          {video.topics.length > 2 && (
            <span className='text-gray-400 dark:text-neutral-muted/80 text-xs'>+{video.topics.length - 2} more</span>
          )}
        </div>

        {/* Stats */}
        <div className='flex items-center justify-between text-sm text-gray-500 dark:text-neutral-muted/80'>
          <div className='flex items-center gap-4'>
            <div className='flex items-center gap-1'>
              <Eye size={14} />
              {video.views}
            </div>
            <div className='flex items-center gap-1'>
              <Star size={14} className='text-yellow-400' />
              {video.rating}
            </div>
          </div>
          <div className='flex items-center gap-1'>
            <Clock size={14} />
            {video.duration}
          </div>
        </div>
      </div>
    </motion.div>
  );
}
