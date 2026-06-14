/**
 * prose.tsx — turn a Constitution paragraph into clickable JSX.
 *
 * Two transforms compose in a single pass so they don't fight each
 * other and produce double-wrapped markup:
 *   1. Cross-references — "Article 152", "Articles 154", "Chapter 12" —
 *      become buttons that invoke the caller's navigate handler.
 *   2. Search highlight — a case-insensitive literal match for `query`
 *      gets wrapped in <mark>.
 *
 * Unknown article/chapter numbers (e.g. a typo in the JSON) are left
 * as plain text, so we never ship a dead link.
 */
import type React from 'react';

import { CONSTITUTION_META, findChapterForArticle } from '@/data/constitution';

/**
 * Primary match — anchors the chain on an explicit keyword:
 *   - "Article 152"       → article 152, no clauses
 *   - "Articles 156"      → article 156 (plural form), no clauses
 *   - "Article 142(2)"    → article 142, clauses = ['2']
 *   - "Article 136(2)(a)" → article 136, clauses = ['2', 'a']
 *   - "Chapter 12"        → chapter 12
 *
 * The third capture group greedily collects zero-or-more parenthesised
 * clause markers so we can jump to a specific subparagraph when the
 * reference names one. Extracted via extractClauses() since the group
 * captures the whole "(2)(a)" blob.
 *
 * Skipped by design:
 *   - clause markers like "(1)", "(a)", "sub-paragraph (i)" — these
 *     are intra-article and have no useful navigation target.
 *   - phrases like "this Constitution" — self-referential.
 */
const REF_RE =
  /\b(Article|Articles|Chapter|Chapters)\s+(\d+)((?:\([A-Za-z0-9]+\))*)/g;

/**
 * After a primary match, prose often continues with more bare numbers
 * joined by ", ", " or ", " and ", or some combination ("Articles 152,
 * 154, 155 and 156"). CONTINUATION_RE eats ONE of those separators
 * plus the next number; we apply it repeatedly until the chain breaks
 * so every number in a list becomes clickable under the same kind as
 * the anchor. Continuation numbers can carry their own subparagraph
 * markers too (rarely: "Article 136(2)(a) or 137(1)").
 */
const CONTINUATION_RE =
  /^(?:,\s+and\s+|,\s*|\s+and\s+|\s+or\s+)(\d+)((?:\([A-Za-z0-9]+\))*)/i;

/** Turn a captured "(2)(a)" blob into ['2', 'a']. Empty string → [].
 * Uses an exec loop rather than [...matchAll(...)] because this repo's
 * tsconfig target doesn't include downlevelIteration support for the
 * RegExpStringIterator return type. */
function extractClauses(parenBlob: string | undefined): string[] {
  if (!parenBlob) return [];
  const out: string[] = [];
  const re = /\(([A-Za-z0-9]+)\)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(parenBlob)) !== null) {
    out.push(m[1]!);
  }
  return out;
}

export type ReferenceTarget =
  | {
      kind: 'article';
      articleNumber: number;
      chapterNumber: number;
      /** Parsed clause path — e.g. ["3"] for "Article 144(3)" or
       * ["3", "c"] for "Article 144(3)(c)". Top-level entry is the
       * paragraph to scroll to / flash on arrival. Empty when the
       * reference didn't name a clause. */
      clauses: string[];
    }
  | { kind: 'chapter'; chapterNumber: number };

interface RenderProseOptions {
  query?: string;
  onRefClick?: (target: ReferenceTarget) => void;
}

/** Single entry point — returns JSX ready to splat into a <p>. */
export function renderProse(
  text: string,
  { query, onRefClick }: RenderProseOptions = {},
): React.ReactNode {
  const refs = findReferences(text);
  const out: React.ReactNode[] = [];
  let cursor = 0;
  let key = 0;

  for (const ref of refs) {
    // Plain text before this reference — still needs search-highlight.
    if (ref.start > cursor) {
      out.push(
        <span key={`t-${key++}`}>
          {highlightSearch(text.slice(cursor, ref.start), query)}
        </span>,
      );
    }
    const label = text.slice(ref.start, ref.end);
    if (ref.target && onRefClick) {
      out.push(
        <button
          key={`r-${key++}`}
          type='button'
          onClick={() => onRefClick(ref.target!)}
          className='inline rounded px-0.5 font-semibold text-gov-forest dark:text-emerald-100 decoration-gov-forest/40 decoration-dotted underline-offset-2 hover:bg-gov-forest/5 hover:underline focus:outline-none focus:ring-2 focus:ring-gov-forest/30'>
          {highlightSearch(label, query)}
        </button>,
      );
    } else {
      // Unknown article/chapter number — render as plain text so we
      // never ship a button that goes nowhere.
      out.push(
        <span key={`u-${key++}`}>{highlightSearch(label, query)}</span>,
      );
    }
    cursor = ref.end;
  }
  if (cursor < text.length) {
    out.push(
      <span key={`tail-${key++}`}>
        {highlightSearch(text.slice(cursor), query)}
      </span>,
    );
  }
  return <>{out}</>;
}

/* ── internals ── */

interface FoundRef {
  start: number;
  end: number;
  target: ReferenceTarget | null;
}

function findReferences(text: string): FoundRef[] {
  const out: FoundRef[] = [];
  // exec-loop rather than for...of on matchAll — see extractClauses
  // for the tsconfig rationale. Clone the regex so the shared /g
  // state at module level doesn't carry lastIndex across calls.
  const re = new RegExp(REF_RE.source, REF_RE.flags);
  let match: RegExpExecArray | null;
  while ((match = re.exec(text)) !== null) {
    const [whole, kindWord, numStr, parenBlob] = match;
    const n = Number.parseInt(numStr!, 10);
    const clauses = extractClauses(parenBlob);
    const start = match.index;
    const end = start + whole.length;
    const isChapter = kindWord!.toLowerCase().startsWith('chapter');
    out.push({ start, end, target: buildTarget(n, isChapter, clauses) });

    // Chain continuation: "Article 144 or 145 and 146" — each extra
    // number becomes its own clickable ref under the same kind as the
    // anchor. We walk the text after the primary match one continuation
    // at a time until the chain breaks on arbitrary prose.
    let cursor = end;
    while (cursor < text.length) {
      const rest = text.slice(cursor);
      const cont = CONTINUATION_RE.exec(rest);
      if (!cont) break;
      const sep = cont[0]!;
      const numInChain = Number.parseInt(cont[1]!, 10);
      const contClauses = extractClauses(cont[2]);
      // The link's clickable range is just the number (+ any clause
      // parens) — the " or ", ", ", " and " glue stays as plain text
      // so the sentence still reads naturally.
      const numStart = cursor + sep.indexOf(cont[1]!);
      const numEnd = cursor + sep.length;
      out.push({
        start: numStart,
        end: numEnd,
        target: buildTarget(numInChain, isChapter, contClauses),
      });
      cursor += sep.length;
    }
  }
  return out;
}

function buildTarget(
  n: number,
  isChapter: boolean,
  clauses: string[],
): ReferenceTarget | null {
  if (isChapter) {
    return CONSTITUTION_META.some((m) => m.number === n)
      ? { kind: 'chapter', chapterNumber: n }
      : null;
  }
  const meta = findChapterForArticle(n);
  return meta
    ? { kind: 'article', articleNumber: n, chapterNumber: meta.number, clauses }
    : null;
}

/** Cheap case-insensitive token highlight — mirror of the old helper
 * inside ArticleViewer. Kept here so prose rendering is a single pass. */
function highlightSearch(text: string, query?: string): React.ReactNode {
  if (!query || query.length < 2) return text;
  const q = query.trim();
  if (!q) return text;
  const lower = text.toLowerCase();
  const needle = q.toLowerCase();
  const out: React.ReactNode[] = [];
  let i = 0;
  let n = 0;
  while (i < text.length) {
    const j = lower.indexOf(needle, i);
    if (j === -1) {
      out.push(text.slice(i));
      break;
    }
    if (j > i) out.push(text.slice(i, j));
    out.push(
      <mark
        key={`h-${n++}`}
        className='rounded bg-gov-gold/30 px-0.5 text-gov-dark dark:text-white'>
        {text.slice(j, j + q.length)}
      </mark>,
    );
    i = j + q.length;
  }
  return <>{out}</>;
}
