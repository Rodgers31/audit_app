import '@testing-library/jest-dom';
import { fireEvent, render, screen } from '@testing-library/react';
import PendingBillsAgingPanel from '@/app/debt/PendingBillsAgingPanel';
import { readScopedAging } from '@/lib/debt/scopedPendingBillsAging';
import { LangProvider } from '@/lib/i18n/LangProvider';

export const assembly: any = {
  version: 2, scope: 'county_assembly', status: 'qualified', absent_reason: null,
  as_at: '2026-06-30', unit: 'KES', currency: 'KES', complete_total: null,
  artifact_sha256: 'a'.repeat(64), extraction_id: 13,
  source_url: 'https://cob.go.ke/report.pdf', publisher: 'Controller of Budget', table: 'Table 2.12', page: 55,
  reported_total: 6_321_350_000, chart_supported: false,
  coverage: { reported_counties: 47, expected_counties: 47, missing_counties: [], qualified_counties: ['Narok', 'Uasin Gishu'], complete: false, counties_with_all_bands: 45, missing_band_counties: ['Narok','Uasin Gishu'] },
  reader_notes: [{ code: 'reported_assembly_population_only' }, { code: 'bands_differ_from_printed_total' }],
  buckets: ['Under one year','1-2 years','2-3 years','Over 3 years'].map((bucket,i)=>({ bucket, amount: [2_481_980_000,1_780_020_000,639_070_000,1_402_370_000][i], raw_value: `${i}`, absent_reason: null })),
};

test('renders separately sourced assembly bands with correct scope, summary discrepancy and no chart',()=>{
  expect(readScopedAging(assembly,'county_assembly')).not.toBeNull();
  render(<PendingBillsAgingPanel observations={{ county_assembly: assembly } as any}/>);
  fireEvent.change(screen.getByLabelText('Aging population'),{target:{value:'county_assembly'}});
  expect(screen.getByRole('table')).toHaveTextContent('Reported assembly aging');
  expect(screen.getByRole('table')).toHaveTextContent('KES 2,481,980,000');
  expect(screen.getByText(/47 of 47 counties/)).toHaveTextContent('assembly aging total');
  expect(screen.getByText(/These source year bands cover county assemblies only/)).toBeInTheDocument();
  expect(screen.getByText(/bands differ from printed total/)).toBeInTheDocument();
  expect(screen.getByText(/45 of 47 counties/)).toHaveTextContent('Missing bands: Narok, Uasin Gishu');
  expect(screen.getByRole('link')).toHaveTextContent('Table 2.12, PDF p.55');
  expect(screen.queryByRole('img')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Aging population'),{target:{value:'combined'}});
  expect(screen.queryByRole('table')).not.toBeInTheDocument();
});

test('assembly needs its own schema, table and scope; executive evidence cannot be relabelled',()=>{
  for (const change of [{version:1},{scope:'county_executive'},{table:'Table 2.11'},{page:53}])
    expect(readScopedAging({...assembly,...change},'county_assembly')).toBeNull();
});

test('active Swahili covers assembly scope, caption, date and qualifications',()=>{
  localStorage.setItem('auditgava-lang','sw');
  const {unmount}=render(<LangProvider><PendingBillsAgingPanel observations={{county_assembly:assembly} as any}/></LangProvider>);
  fireEvent.change(screen.getByLabelText('Kundi la bili'),{target:{value:'county_assembly'}});
  expect(screen.getByRole('table')).toHaveTextContent('bili za mabunge');
  expect(screen.getByText(/30 Juni 2026/)).toHaveTextContent('Mabunge ya kaunti');
  expect(screen.getByText(/yanahusu mabunge ya kaunti pekee/)).toBeInTheDocument();
  unmount();localStorage.removeItem('auditgava-lang');
});
