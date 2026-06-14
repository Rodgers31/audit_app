/**
 * MapControls - Displays animation mode, interaction hints, and visualization mode toggle
 * Enhanced header overlay for the interactive map
 */
'use client';

import { Eye, EyeOff } from 'lucide-react';

interface MapControlsProps {
  animationMode: 'slideshow' | 'pulse' | 'wave';
  visualMode: 'focus' | 'overview';
  onVisualizationModeChange: (mode: 'focus' | 'overview') => void;
}

export default function MapControls({
  animationMode,
  visualMode,
  onVisualizationModeChange,
}: MapControlsProps) {
  return (
    <div className='absolute top-4 left-4 z-20'>
      <div className='bg-white/90 dark:bg-surface-elevated backdrop-blur-md rounded-lg px-3 py-2 shadow-lg border border-white/20'>
        <div className='flex items-center justify-between gap-3'>
          <div className='flex flex-col'>
            <p className='text-xs text-slate-600 dark:text-neutral-muted font-medium'>
              <span className='capitalize text-blue-600'>{animationMode}</span> mode
            </p>
            <p className='text-xs text-slate-500 dark:text-neutral-muted/80'>Click counties • Hover for details</p>
          </div>

          {/* Visualization Mode Toggle */}
          <button
            onClick={() => onVisualizationModeChange(visualMode === 'focus' ? 'overview' : 'focus')}
            className={`
              flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-medium transition-all duration-200
              ${
                visualMode === 'focus'
                  ? 'bg-blue-500 text-white shadow-sm'
                  : 'bg-gray-100 dark:bg-surface-elevated text-gray-600 dark:text-neutral-muted hover:bg-gray-200 dark:hover:bg-surface-sunken'
              }
            `}
            title={visualMode === 'focus' ? 'Switch to Overview Mode' : 'Switch to Focus Mode'}>
            {visualMode === 'focus' ? (
              <>
                <Eye size={12} />
                Focus
              </>
            ) : (
              <>
                <EyeOff size={12} />
                Overview
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
