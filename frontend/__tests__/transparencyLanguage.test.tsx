import { render, screen } from '@testing-library/react';
import MoneyFlowOverview from '@/components/transparency/MoneyFlowOverview';
import MoneyFlowPeriodPicker from '@/components/transparency/MoneyFlowPeriodPicker';
import { LangProvider } from '@/lib/i18n/LangProvider';

afterEach(() => localStorage.clear());

it('translates the period control and national summary in Swahili', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  render(
    <LangProvider>
      <MoneyFlowPeriodPicker
        years={[{ fiscal_year: '2026/27', is_current: true }]}
        selected='2026/27'
        onSelect={() => {}}
      />
      <MoneyFlowOverview
        insights={{
          allocated: 100,
          spent: 60,
          flagged: null,
          gap: 40,
          unspentPct: 40,
          efficiency: 60,
        }}
        fiscalYear='2026/27'
        projected={false}
      />
    </LangProvider>
  );
  expect(
    screen.getByRole('combobox', { name: 'Mwaka wa fedha na kipindi cha ripoti' })
  ).toHaveValue('2026/27');
  expect(screen.getByRole('option')).toHaveTextContent('Unaendelea');
  expect(screen.getByRole('region', { name: 'Kwa muhtasari' })).toHaveTextContent(
    'Jumla iliyotengwa'
  );
  expect(screen.queryByText('Total allocated')).not.toBeInTheDocument();
  expect(screen.getByText('Kiasi hakipatikani')).toBeInTheDocument();
});

it('uses plain-language descriptions without changing the displayed amounts', () => {
  localStorage.setItem('auditgava-lang', 'plain');
  render(
    <LangProvider>
      <MoneyFlowOverview
        insights={{
          allocated: 100,
          spent: 60,
          flagged: 0,
          gap: 40,
          unspentPct: 40,
          efficiency: 60,
        }}
        fiscalYear='2026/27'
        projected={false}
      />
    </LangProvider>
  );
  expect(screen.getByText('Money set aside')).toBeInTheDocument();
  expect(screen.getByText('Money left to spend')).toBeInTheDocument();
  expect(screen.getByRole('region')).toHaveTextContent('KES 100');
  expect(screen.getByRole('region')).toHaveTextContent('KES 0');
});


it('renders new amount coverage in Swahili beside a partial zero', () => {
  localStorage.setItem('auditgava-lang', 'sw');
  render(<LangProvider><MoneyFlowOverview fiscalYear='2024/25' projected={false} insights={{
    allocated: 100, spent: 60, flagged: 0, gap: 40, unspentPct: 40, efficiency: 60,
    audit_amount_coverage: {
      status: 'partial', reason: 'incomplete_amount_coverage', total_findings: 2,
      findings_with_amount: 1, findings_without_amount: 1, findings_with_invalid_amount: 0,
      withheld_findings: 0,
    },
  }} /></LangProvider>);
  expect(document.body.textContent).toContain('KES 0');
  expect(document.body.textContent).toContain('Jumla ya sehemu: Matokeo 1 kati ya 2');
  expect(document.body.textContent).not.toContain('Partial subtotal');
});
