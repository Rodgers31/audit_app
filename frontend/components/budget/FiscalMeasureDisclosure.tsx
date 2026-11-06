import type { FiscalMeasureQualification, FiscalTaxObservation } from '@/lib/api/fiscal';

const LABELS: Record<string, string> = {
  appropriated_budget: 'Approved gross budget',
  total_revenue: 'Ordinary revenue, excluding A-i-A and grants',
  tax_revenue: 'Tax revenue',
  non_tax_revenue: 'Non-tax revenue',
  debt_service_cost: 'Debt service, interest and principal',
  debt_service_per_shilling: 'Debt service per KES 100 of ordinary revenue',
};

export default function FiscalMeasureDisclosure({ qualifications, absentReasons, taxObservation }: {
  qualifications?: Record<string, FiscalMeasureQualification>;
  absentReasons?: Record<string, string>;
  taxObservation?: FiscalTaxObservation | null;
}) {
  if (!qualifications && !absentReasons && !taxObservation) return null;
  return (
    <details className='mt-3 text-xs leading-relaxed text-neutral-muted'>
      <summary className='cursor-pointer font-medium text-gov-forest dark:text-emerald-100'>
        Sources and withheld figures
      </summary>
      <ul className='mt-2 space-y-2'>
        {Object.entries(LABELS).map(([field, label]) => {
          const proof = qualifications?.[field];
          if (proof) return (
            <li key={field}>
              <span className='font-medium'>{label}:</span>{' '}
              {proof.vintage}; printed precision KES {proof.precision_kes.toLocaleString('en-KE')}.{' '}
              <a className='underline' href={proof.source.url} target='_blank' rel='noopener noreferrer'>
                {proof.source.title ?? 'Source document'} · {proof.source.page}
              </a>
            </li>
          );
          if (!absentReasons?.[field]) return null;
          return <li key={field}>{label}: withheld because compatible source evidence is unconfirmed. Missing values are not zero.</li>;
        })}
      </ul>
      {taxObservation && <p className='mt-2'>
        Separate BROP preliminary observation for {taxObservation.fiscal_year}: ordinary revenue KES {taxObservation.ordinary_revenue_billion.toLocaleString('en-KE')}B,
        tax KES {taxObservation.tax_revenue_billion.toLocaleString('en-KE')}B and non-tax KES {taxObservation.non_tax_revenue_billion.toLocaleString('en-KE')}B.
        Printed precision: KES 1B. {taxObservation.disclosure}{' '}
        <a className='underline' href={taxObservation.source.url} target='_blank' rel='noopener noreferrer'>{taxObservation.source.title} · {taxObservation.source.page}</a>
      </p>}

    </details>
  );
}
