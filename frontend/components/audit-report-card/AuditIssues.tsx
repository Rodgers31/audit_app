/**
 * Audit issues section for detailed audit problems
 */
import { County } from '@/types';
import { formatCurrency } from './auditUtils';

interface AuditIssuesProps {
  auditIssues?: County['auditIssues'];
}

export default function AuditIssues({ auditIssues }: AuditIssuesProps) {
  if (!auditIssues || auditIssues.length === 0) {
    return null;
  }

  const getSeverityClass = (severity: string) => {
    switch (severity) {
      case 'critical':
        return 'bg-red-100 text-red-800';
      case 'high':
        return 'bg-orange-100 text-orange-800';
      case 'medium':
        return 'bg-yellow-100 text-yellow-800';
      default:
        return 'bg-blue-100 text-blue-800';
    }
  };

  return (
    <div>
      <h5 className='text-lg font-semibold text-gray-900 dark:text-neutral-text mb-4'>Specific Issues Found</h5>
      <div className='space-y-3'>
        {auditIssues.map((issue) => (
          <div key={issue.id} className='p-4 bg-yellow-50 border border-yellow-200 rounded-xl'>
            <div className='flex items-start justify-between mb-2'>
              <span
                className={`text-xs px-2 py-1 rounded-full font-medium ${getSeverityClass(
                  issue.severity
                )}`}>
                {issue.severity.toUpperCase()} PRIORITY
              </span>
              {issue.amount && (
                <span className='text-sm font-semibold text-gray-700 dark:text-neutral-muted'>
                  {formatCurrency(issue.amount)}
                </span>
              )}
            </div>
            <p className='text-gray-700 dark:text-neutral-muted'>{issue.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
