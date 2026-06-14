/**
 * Debug component to display all API endpoints
 * Useful for development and debugging
 */
'use client';

import { API_ENDPOINTS, getApiBaseUrl, logAllEndpoints } from '@/lib/api/endpoints';
import { useState } from 'react';

export function EndpointsDebugger() {
  const [isOpen, setIsOpen] = useState(false);

  const handleLogEndpoints = () => {
    logAllEndpoints();
  };

  if (process.env.NODE_ENV !== 'development') {
    return null;
  }

  return (
    <div className='fixed bottom-4 right-4 z-50'>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className='bg-blue-600 text-white px-4 py-2 rounded-lg shadow-lg hover:bg-blue-700 transition-colors'>
        🔗 API Endpoints
      </button>

      {isOpen && (
        <div className='absolute bottom-12 right-0 w-96 max-h-96 overflow-y-auto bg-white dark:bg-surface-base border border-gray-300 dark:border-neutral-border rounded-lg shadow-xl p-4'>
          <div className='flex justify-between items-center mb-4'>
            <h3 className='font-bold text-lg'>API Endpoints</h3>
            <button onClick={() => setIsOpen(false)} className='text-gray-500 dark:text-neutral-muted/80 hover:text-gray-700 dark:text-neutral-muted'>
              ✕
            </button>
          </div>

          <div className='space-y-4'>
            <div>
              <p className='text-sm text-gray-600 dark:text-neutral-muted mb-2'>
                <strong>Base URL:</strong> {getApiBaseUrl()}
              </p>
              <button
                onClick={handleLogEndpoints}
                className='text-xs bg-gray-100 dark:bg-surface-elevated px-2 py-1 rounded hover:bg-gray-200 dark:bg-surface-sunken'>
                Log to Console
              </button>
            </div>

            <div className='space-y-3'>
              {/* Counties Endpoints */}
              <div>
                <h4 className='font-semibold text-sm text-blue-600 mb-1'>Counties</h4>
                <ul className='text-xs space-y-1 text-gray-700 dark:text-neutral-muted'>
                  {Object.entries(API_ENDPOINTS.COUNTIES).map(([key, value]) => (
                    <li key={key} className='font-mono'>
                      <span className='text-purple-600'>{key}:</span>{' '}
                      {typeof value === 'function' ? `function()` : value}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Audits Endpoints */}
              <div>
                <h4 className='font-semibold text-sm text-green-600 mb-1'>Audits</h4>
                <ul className='text-xs space-y-1 text-gray-700 dark:text-neutral-muted'>
                  {Object.entries(API_ENDPOINTS.AUDITS).map(([key, value]) => (
                    <li key={key} className='font-mono'>
                      <span className='text-purple-600'>{key}:</span>{' '}
                      {typeof value === 'function' ? `function()` : value}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Budget Endpoints */}
              <div>
                <h4 className='font-semibold text-sm text-orange-600 mb-1'>Budget</h4>
                <ul className='text-xs space-y-1 text-gray-700 dark:text-neutral-muted'>
                  {Object.entries(API_ENDPOINTS.BUDGET).map(([key, value]) => (
                    <li key={key} className='font-mono'>
                      <span className='text-purple-600'>{key}:</span>{' '}
                      {typeof value === 'function' ? `function()` : value}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Debt Endpoints */}
              <div>
                <h4 className='font-semibold text-sm text-red-600 mb-1'>Debt</h4>
                <ul className='text-xs space-y-1 text-gray-700 dark:text-neutral-muted'>
                  {Object.entries(API_ENDPOINTS.DEBT).map(([key, value]) => (
                    <li key={key} className='font-mono'>
                      <span className='text-purple-600'>{key}:</span>{' '}
                      {typeof value === 'function' ? `function()` : value}
                    </li>
                  ))}
                </ul>
              </div>

              {/* Statistics Endpoints */}
              <div>
                <h4 className='font-semibold text-sm text-indigo-600 mb-1'>Statistics</h4>
                <ul className='text-xs space-y-1 text-gray-700 dark:text-neutral-muted'>
                  {Object.entries(API_ENDPOINTS.STATISTICS).map(([key, value]) => (
                    <li key={key} className='font-mono'>
                      <span className='text-purple-600'>{key}:</span>{' '}
                      {typeof value === 'function' ? `function()` : value}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default EndpointsDebugger;
