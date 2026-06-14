/**
 * CountyHeader - Header section with county name, population, and audit status
 * Displays key county identification and latest audit information
 */
'use client';

import { County } from '@/types';
import { AlertTriangle, Users } from 'lucide-react';
import { formatPopulation, getAuditStatusTextColor } from './countyUtils';

interface CountyHeaderProps {
  county: County;
}

export default function CountyHeader({ county }: CountyHeaderProps) {
  const status = county.auditStatus || 'pending';
  return (
    <div className='flex items-center justify-between mb-6'>
      {/* County Info */}
      <div>
        <h1 className='text-2xl font-semibold text-gray-900 dark:text-neutral-text mb-1'>{county.name} County</h1>
        <div className='flex items-center gap-2 text-gray-600 dark:text-neutral-muted'>
          <Users size={16} />
          <span className='text-base'>Population: {formatPopulation(county.population)}</span>
        </div>
      </div>

      {/* Audit Status Badge */}
      <div
        className={`px-4 py-2 rounded-lg border ${
          status === 'clean'
            ? 'bg-green-50 border-green-200'
            : status === 'qualified'
            ? 'bg-yellow-50 border-yellow-200'
            : status === 'adverse'
            ? 'bg-red-50 border-red-200'
            : 'bg-orange-50 border-orange-200'
        }`}>
        <div className='flex items-center gap-2'>
          <AlertTriangle size={16} className={getAuditStatusTextColor(status)} />
          <span
            className={`font-medium text-sm ${
              status === 'clean'
                ? 'text-green-700'
                : status === 'qualified'
                ? 'text-yellow-700'
                : status === 'adverse'
                ? 'text-red-700'
                : 'text-orange-700'
            }`}>
            {status} Audit (2024)
          </span>
        </div>
      </div>
    </div>
  );
}
