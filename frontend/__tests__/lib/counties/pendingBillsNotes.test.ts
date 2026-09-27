/**
 * The words beside a county's pending-bills figure (#238): its date, its
 * table, and what the Controller of Budget's report says about it.
 */
import {
  formatAsAt,
  pendingBillsAbsenceLine,
  pendingBillsAsAtLine,
  pendingBillsNoteLines,
} from '@/lib/counties/pendingBillsNotes';
import { MESSAGES, type TranslationKey } from '@/lib/i18n/messages';

const en = (key: TranslationKey) => MESSAGES[key].en;
const sw = (key: TranslationKey) => MESSAGES[key].sw;
const fmt = (n: number) => `KES ${(n / 1e9).toFixed(2)}B`;

describe('the as-at line', () => {
  it('names the day and the table', () => {
    expect(pendingBillsAsAtLine('2026-06-30', 'Table 2.10', 'en', en)).toBe(
      'As at 30 June 2026 · Controller of Budget, Table 2.10'
    );
  });

  it('is absent rather than guessed when the API sends no date', () => {
    expect(pendingBillsAsAtLine(null, 'Table 2.10', 'en', en)).toBeNull();
    expect(pendingBillsAsAtLine('FY 2025/26', 'Table 2.10', 'en', en)).toBeNull();
    expect(formatAsAt('2026-13-45', 'en')).toBeNull();
  });

  it('is written in the reader’s language', () => {
    const line = pendingBillsAsAtLine('2026-06-30', 'Table 2.10', 'sw', sw);
    expect(line).toMatch(/^Hadi 30 /);
    expect(line).toContain('Mdhibiti wa Bajeti');
  });

  it.each(['2026-02-29', '2026-02-30', '2026-04-31', '1900-02-29'])(
    'rejects impossible calendar date %s without shifting the reported day', (iso) => {
      expect(formatAsAt(iso, 'en')).toBeNull();
      expect(pendingBillsAsAtLine(iso, 'Table 2.10', 'en', en)).toBeNull();
      expect(pendingBillsAbsenceLine({ reason: 'not_reported', as_at: iso }, 'en', en)).toBeNull();
    }
  );

  it.each(['2024-02-29', '2000-02-29'])(
    'preserves the real leap day %s', (iso) => {
      expect(formatAsAt(iso, 'en')).toBe(`29 February ${iso.slice(0, 4)}`);
    }
  );
});

describe('the notes', () => {
  const uasinGishu = [
    { code: 'assembly_not_printed', table: 'Table 2.10' },
    {
      code: 'chapter_table_differs',
      table: 'Table 2.10',
      chapter_table: 'Table 3.678',
      chapter_total: '1481440000.00',
    },
  ];

  it('words each note the report makes, with its figures', () => {
    const lines = pendingBillsNoteLines(uasinGishu, en, fmt);
    expect(lines).toHaveLength(2);
    expect(lines[0]).toContain('no County Assembly figure');
    expect(lines[1]).toContain('KES 1.48B');
    expect(lines[1]).toContain('Table 3.678');
    expect(lines.join(' ')).not.toMatch(/\{\w+\}/);
  });

  it('drops a code it cannot word, and a mismatch with no amount', () => {
    expect(
      pendingBillsNoteLines(
        [{ code: 'made_up' }, { code: 'chapter_table_differs', chapter_total: 'NaN' }],
        en,
        fmt
      )
    ).toEqual([]);
    expect(pendingBillsNoteLines(undefined, en, fmt)).toEqual([]);
  });

  it('never calls the figures audited', () => {
    for (const lang of ['en', 'sw', 'plain'] as const) {
      expect(MESSAGES['counties.provenance.rest'][lang]).not.toMatch(/audited|zilizokaguliwa/i);
    }
  });
});

describe('the reason there is no figure', () => {
  it('says the county did not report, and when', () => {
    expect(
      pendingBillsAbsenceLine({ reason: 'not_reported', as_at: '2026-06-30', table: 'Table 2.10' }, 'en', en)
    ).toBe('Not reported to the Controller of Budget as at 30 June 2026 (Table 2.10).');
  });

  it('says nothing for a reason it does not know or a missing date', () => {
    expect(pendingBillsAbsenceLine({ reason: 'lost', as_at: '2026-06-30' }, 'en', en)).toBeNull();
    expect(pendingBillsAbsenceLine({ reason: 'not_reported', as_at: null }, 'en', en)).toBeNull();
    expect(pendingBillsAbsenceLine(null, 'en', en)).toBeNull();
  });
});
