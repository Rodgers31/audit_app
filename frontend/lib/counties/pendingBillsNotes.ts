/**
 * The words beside a county's pending-bills figure: the day it is a stock on,
 * where it is printed, and what the report says about it (#238).
 *
 * The figure is each county's trade payables at 30 June, from the Controller
 * of Budget's full-year County Governments Budget Implementation Review
 * Report. The API sends the date, the table and note CODES; the words live in
 * lib/i18n/messages so they are translated like the rest of the page.
 */
import type { Lang, TranslationKey } from '@/lib/i18n/messages';

export type PendingBillsNote =
  | { code: 'cob_marked_inconsistent'; table?: string | null }
  | { code: 'assembly_not_printed'; table?: string | null }
  | {
      code: 'chapter_table_differs';
      table?: string | null;
      chapter_table?: string | null;
      chapter_page?: number | null;
      /** Whole shillings, as a decimal string. */
      chapter_total?: string | null;
    };

type Translate = (key: TranslationKey) => string;

const NOTE_KEYS: Record<PendingBillsNote['code'], TranslationKey> = {
  cob_marked_inconsistent: 'county.overview.pending_note.cob_marked_inconsistent',
  assembly_not_printed: 'county.overview.pending_note.assembly_not_printed',
  chapter_table_differs: 'county.overview.pending_note.chapter_table_differs',
};

function fill(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in values ? values[name] : whole
  );
}

/** "30 June 2026" from "2026-06-30"; null for anything that is not a date. */
export function formatAsAt(iso: string | null | undefined, lang: Lang): string | null {
  if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
  const when = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(when.getTime())) return null;
  return when.toLocaleDateString(lang === 'sw' ? 'sw-KE' : 'en-GB', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/**
 * "As at 30 June 2026 · Controller of Budget, Table 2.10", or null when the
 * API sent no date — the line is never shown with a guessed one.
 */
export function pendingBillsAsAtLine(
  asAt: string | null | undefined,
  table: string | null | undefined,
  lang: Lang,
  t: Translate
): string | null {
  const date = formatAsAt(asAt, lang);
  if (!date) return null;
  return fill(t('county.overview.pending_as_at'), { date, table: table || '' })
    .replace(/,\s*$/, '')
    .replace(/\s*\(\)/, '');
}

/**
 * Why there is no figure, in the report's own terms — "Not reported to the
 * Controller of Budget as at 30 June 2026 (Table 2.10)" for Nandi — or null
 * for a bare absence the report says nothing about.
 */
export function pendingBillsAbsenceLine(
  absence: { reason?: unknown; as_at?: unknown; table?: unknown } | null | undefined,
  lang: Lang,
  t: Translate
): string | null {
  if (!absence) return null;
  const key: TranslationKey | null =
    absence.reason === 'not_reported'
      ? 'county.overview.pending_absent.not_reported'
      : absence.reason === 'withheld'
        ? 'county.overview.pending_absent.withheld'
        : null;
  const date = formatAsAt(typeof absence.as_at === 'string' ? absence.as_at : null, lang);
  if (!key || !date) return null;
  return fill(t(key), { date, table: typeof absence.table === 'string' ? absence.table : '' })
    .replace(/\s*\(\)/, '')
    .replace(/\(,\s*/, '(');
}

/**
 * One sentence per note the page knows how to word. A code it does not know
 * is dropped rather than shown raw; the API already passes known codes only.
 */
export function pendingBillsNoteLines(
  notes: ReadonlyArray<{ code?: unknown } & Record<string, unknown>> | null | undefined,
  t: Translate,
  fmtAmount: (n: number) => string
): string[] {
  const lines: string[] = [];
  for (const note of notes ?? []) {
    const code = note?.code;
    if (typeof code !== 'string' || !(code in NOTE_KEYS)) continue;
    const key = NOTE_KEYS[code as PendingBillsNote['code']];
    const amount = Number(note.chapter_total);
    if (code === 'chapter_table_differs' && !Number.isFinite(amount)) continue;
    lines.push(
      fill(t(key), {
        table: String(note.table ?? ''),
        chapter_table: String(note.chapter_table ?? ''),
        amount: Number.isFinite(amount) ? fmtAmount(amount) : '',
      })
    );
  }
  return lines;
}
