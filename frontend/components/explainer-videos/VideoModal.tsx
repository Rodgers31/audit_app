/**
 * VideoModal - Modal component for displaying video details and player
 * Shows expanded video information including learning objectives and topics
 */
'use client';

import { motion } from 'framer-motion';
import { Play } from 'lucide-react';
import { ExplainerVideo } from '../../data/explainerVideos';

interface VideoModalProps {
  video: ExplainerVideo | null;
  isOpen: boolean;
  onClose: () => void;
}

export default function VideoModal({ video, isOpen, onClose }: VideoModalProps) {
  if (!isOpen || !video) return null;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className='fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4'
      onClick={onClose}>
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className='bg-white dark:bg-surface-base rounded-2xl p-8 max-w-2xl w-full max-h-[90vh] overflow-y-auto'
        onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div className='flex items-center justify-between mb-6'>
          <h3 className='text-2xl font-bold text-gray-900 dark:text-neutral-text'>{video.title}</h3>
          <button onClick={onClose} className='text-gray-400 dark:text-neutral-muted/80 hover:text-gray-600 dark:text-neutral-muted text-2xl'>
            ×
          </button>
        </div>

        {/* Video Player Placeholder */}
        <div className='bg-gray-100 dark:bg-surface-elevated rounded-xl h-64 flex items-center justify-center mb-6'>
          <div className='text-center'>
            <Play size={48} className='text-gray-400 dark:text-neutral-muted/80 mx-auto mb-2' />
            <p className='text-gray-600 dark:text-neutral-muted'>Video Player Placeholder</p>
            <p className='text-sm text-gray-500 dark:text-neutral-muted/80'>Duration: {video.duration}</p>
          </div>
        </div>

        {/* Video Details */}
        <div className='space-y-6'>
          {/* Description */}
          <div>
            <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>Description</h4>
            <p className='text-gray-700 dark:text-neutral-muted'>{video.description}</p>
          </div>

          {/* Key Learnings */}
          <div>
            <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>What You'll Learn</h4>
            <ul className='space-y-1'>
              {video.keyLearnings.map((learning, i) => (
                <li key={i} className='flex items-start gap-2 text-gray-700 dark:text-neutral-muted'>
                  <span className='text-green-500 mt-1'>✓</span>
                  <span className='text-sm'>{learning}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* Topics Covered */}
          <div>
            <h4 className='font-semibold text-gray-900 dark:text-neutral-text mb-2'>Topics Covered</h4>
            <div className='flex flex-wrap gap-2'>
              {video.topics.map((topic) => (
                <span
                  key={topic}
                  className='bg-blue-100 text-blue-800 px-3 py-1 rounded-lg text-sm'>
                  {topic}
                </span>
              ))}
            </div>
          </div>

          {/* Video Metadata */}
          <div className='bg-gray-50 dark:bg-surface-elevated rounded-lg p-4'>
            <div className='grid grid-cols-2 gap-4 text-sm'>
              <div>
                <span className='font-medium text-gray-600 dark:text-neutral-muted'>Duration:</span>
                <span className='ml-2 text-gray-900 dark:text-neutral-text'>{video.duration}</span>
              </div>
              <div>
                <span className='font-medium text-gray-600 dark:text-neutral-muted'>Difficulty:</span>
                <span
                  className={`ml-2 px-2 py-1 rounded text-xs ${
                    video.difficulty === 'beginner'
                      ? 'bg-green-100 text-green-800'
                      : video.difficulty === 'intermediate'
                      ? 'bg-orange-100 text-orange-800'
                      : 'bg-red-100 text-red-800'
                  }`}>
                  {video.difficulty}
                </span>
              </div>
              <div>
                <span className='font-medium text-gray-600 dark:text-neutral-muted'>Views:</span>
                <span className='ml-2 text-gray-900 dark:text-neutral-text'>{video.views}</span>
              </div>
              <div>
                <span className='font-medium text-gray-600 dark:text-neutral-muted'>Rating:</span>
                <span className='ml-2 text-gray-900 dark:text-neutral-text'>{video.rating}/5</span>
              </div>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
