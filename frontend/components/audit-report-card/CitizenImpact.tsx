/**
 * Citizen impact section for audit reports
 */
import { CheckCircle } from 'lucide-react';
import { getCitizenImpactMessage } from './auditUtils';

interface CitizenImpactProps {
  auditStatus?: string;
}

export default function CitizenImpact({ auditStatus = 'pending' }: CitizenImpactProps) {
  return (
    <div>
      <h5 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4 flex items-center gap-2'>
        <CheckCircle size={20} className='text-indigo-600' />
        What This Means for Citizens
      </h5>
      <div className='p-4 bg-indigo-50 rounded-xl border border-indigo-200'>
        <p className='text-indigo-800 leading-relaxed'>{getCitizenImpactMessage(auditStatus)}</p>
      </div>
    </div>
  );
}
