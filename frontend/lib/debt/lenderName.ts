/**
 * Display formatting for creditor names.
 *
 * World Bank IDS pads its creditor labels to a fixed column width with
 * non-breaking spaces, and the seeding writer stores them verbatim. Production
 * therefore serves — and /debt renders — names like:
 *
 *   "Multilateral (World Bank-IDA  …25 of them… )"
 *   "Multilateral (African Dev. Bank         )"
 *
 * DISPLAY ONLY. The stored string is the join key `reconcile_external_creditors`
 * matches on when it decides which creditor row to update, so trimming it at
 * the source would orphan every existing row. Nothing here writes back — the
 * transform is applied at render, and the value that reaches the API is
 * untouched.
 *
 * Note the padding is INTERIOR: it sits before the closing parenthesis, so
 * `String.prototype.trim()` — which does remove U+00A0 — cannot reach it. The
 * runs have to be collapsed, not trimmed.
 */

/**
 * Whitespace the source uses that a reader cannot see and `\s` does not fully
 * cover: NBSP, narrow NBSP, figure/thin/hair spaces, and the zero-width and
 * BOM characters that survive copy-paste out of a PDF.
 */
const INVISIBLE_SPACE = /[\u00a0\u1680\u2000-\u200a\u202f\u205f\u3000]/g;
const ZERO_WIDTH = /[\u200b-\u200d\ufeff]/g;

/**
 * The creditor name as it should appear on screen.
 *
 * Collapses every run of whitespace — visible or not — to a single space,
 * closes up padding inside brackets, and trims. Returns '' for an absent name
 * so callers can test for it; it never invents a placeholder, because an
 * unnamed creditor is a gap in the data, not a creditor called "Unknown".
 */
export function displayLenderName(raw: string | null | undefined): string {
  if (typeof raw !== 'string') return '';
  return raw
    .replace(ZERO_WIDTH, '')
    .replace(INVISIBLE_SPACE, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\(\s+/g, '(')
    .replace(/\s+\)/g, ')')
    .trim();
}
