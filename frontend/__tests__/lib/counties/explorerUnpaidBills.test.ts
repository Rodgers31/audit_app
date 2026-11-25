import { transformCountyData } from '@/lib/api/counties';
import { countyUnpaidBills, unpaidBillsTone } from '@/lib/counties/explorerUnpaidBills';

const asAt = '2026-06-30';
const source = {
  publisher: 'Controller of Budget',
  title: 'County Governments Budget Implementation Review Report, FY2025/26',
  table: 'Table 2.10',
  url: 'https://cob.go.ke/synthetic-county-payables.pdf',
};

function county(id: string, overrides: Record<string, unknown> = {}) {
  return transformCountyData({
    id,
    name: id,
    budget_2025: 0,
    population: null,
    pending_bills: 0,
    pending_bills_as_at: asAt,
    pending_bills_selection: { as_at: asAt },
    pending_bills_source: source,
    ...overrides,
  });
}

describe('County Explorer unpaid bills', () => {
  it('preserves official figures including zero on the comparable date, beside gaps and older amounts', () => {
    const notes = [{ code: 'assembly_not_printed', table: source.table }];
    const measure = countyUnpaidBills([
      county('Mombasa', { pending_bills: 720_000_000, pending_bills_notes: notes }),
      county('Kisumu'),
      county('Nandi', { pending_bills: null, pending_bills_as_at: null, pending_bills_source: null }),
      county('Baringo', { pending_bills: 900_000_000, pending_bills_as_at: '2025-06-30' }),
    ]);
    expect(measure.asAt).toBe(asAt);
    expect(measure.maximum).toBe(720_000_000);
    expect(Array.from(measure.amounts.keys())).toEqual(['Mombasa', 'Kisumu']);
    expect(measure.amounts.get('Mombasa')).toEqual({
      value: 720_000_000,
      sourceUrl: source.url,
      sourceTable: source.table,
      notes,
    });
    expect(measure.amounts.get('Kisumu')?.value).toBe(0);
    expect(unpaidBillsTone(0, measure.maximum)).toBe(1);
    expect(unpaidBillsTone(measure.maximum, measure.maximum)).toBe(4);
    expect(unpaidBillsTone(undefined, measure.maximum)).toBe('unavailable');
  });

  it.each([undefined, null, '2026-02-30'])('suppresses all figures without a valid common selection date (%s)', date => {
    const measure = countyUnpaidBills([county('Nairobi', { pending_bills_selection: { as_at: date } })]);
    expect(measure.asAt).toBeUndefined();
    expect(measure.amounts.size).toBe(0);
  });

  it('keeps the reporting date when every figure is withheld', () => {
    const measure = countyUnpaidBills([county('Nandi', { pending_bills: null, pending_bills_as_at: null })]);
    expect(measure.asAt).toBe(asAt);
    expect(measure.amounts.size).toBe(0);
  });

  it('suppresses conflicting selection dates across counties', () => {
    const measure = countyUnpaidBills([
      county('Mombasa'),
      county('Nandi', { pending_bills: null, pending_bills_selection: { as_at: '2025-06-30' } }),
    ]);
    expect(measure.asAt).toBeUndefined();
    expect(measure.amounts.size).toBe(0);
  });

  it.each(['https://example.com/report.pdf', 'http://cob.go.ke/report.pdf', 'https://cob.go.ke.example.com/report.pdf', null])(
    'withholds amounts without an official report URL (%s)',
    url => {
      const measure = countyUnpaidBills([county('Nairobi', { pending_bills_source: { ...source, url } })]);
      expect(measure.amounts.size).toBe(0);
    }
  );
});
