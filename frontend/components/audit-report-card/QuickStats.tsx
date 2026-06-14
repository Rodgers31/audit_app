/**
 * Quick statistics display for county audit reports
 */
import { County } from '@/types';
import { Calendar, DollarSign, Users } from 'lucide-react';
import { formatCurrency, formatDate } from './auditUtils';

interface QuickStatsProps {
  county: County;
}

export default function QuickStats({ county }: QuickStatsProps) {
  return (
    <div className='grid grid-cols-1 md:grid-cols-3 gap-4 mb-4'>
      <div className='flex items-center gap-2 text-sm text-gray-600 dark:text-neutral-muted'>
        <DollarSign size={16} className='text-blue-600' />
        <span>Budget: {formatCurrency(county.budget ?? county.totalBudget ?? 0)}</span>
      </div>
      <div className='flex items-center gap-2 text-sm text-gray-600 dark:text-neutral-muted'>
        <Users size={16} className='text-purple-600' />
        <span>
          Population:{' '}
          {county.population && county.population > 0
            ? (county.population / 1e6).toFixed(1)
            : 'N/A'}
          M
        </span>
      </div>
      <div className='flex items-center gap-2 text-sm text-gray-600 dark:text-neutral-muted'>
        <Calendar size={16} className='text-green-600' />
        <span>Last Audit: {county.lastAuditDate ? formatDate(county.lastAuditDate) : 'N/A'}</span>
      </div>
    </div>
  );
}
