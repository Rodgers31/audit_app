#!/usr/bin/env node
/**
 * Parse the full Constitution of Kenya (2010) from Wikisource wikitext
 * into our chapter-N.json schema.
 *
 *   input:  a cached wikitext JSON blob (see WIKITEXT_SRC below)
 *   output: public/data/constitution/chapter-{1..18}.json
 *           public/data/constitution/schedules.json
 *           .cache/constitution-meta.json  (for pasting into index.ts)
 *
 * Behaviour:
 *   - Re-parses every chapter, so content is always in sync with the source.
 *   - Merges hand-authored editorial fields (summary, explanation, tags,
 *     chapter.summary) from any existing chapter-N.json at the target path,
 *     matched on article number. Parsed paragraphs always overwrite.
 *
 * Run:
 *   node scripts/build-constitution.mjs             # uses cached wikitext
 *   FETCH=1 node scripts/build-constitution.mjs     # re-fetch from Wikisource
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const DATA_DIR = join(ROOT, 'public', 'data', 'constitution');
const CACHE_DIR = join(ROOT, '.cache');
const WIKITEXT_SRC = join(CACHE_DIR, 'coke-wikitext.json');
const META_OUT = join(CACHE_DIR, 'constitution-meta.json');

/* ───────────────────────── Roman numerals ───────────────────────── */

const ROMAN_WORDS = {
  ONE: 1, TWO: 2, THREE: 3, FOUR: 4, FIVE: 5, SIX: 6,
  SEVEN: 7, EIGHT: 8, NINE: 9, TEN: 10, ELEVEN: 11,
  TWELVE: 12, THIRTEEN: 13, FOURTEEN: 14, FIFTEEN: 15,
  SIXTEEN: 16, SEVENTEEN: 17, EIGHTEEN: 18,
};
const ORDINAL_WORDS = {
  FIRST: 1, SECOND: 2, THIRD: 3, FOURTH: 4, FIFTH: 5, SIXTH: 6,
};

/* ───────────────────────── Fetch (optional) ───────────────────────── */

async function fetchWikitext() {
  const url =
    'https://en.wikisource.org/w/api.php' +
    '?action=parse&page=Constitution_of_Kenya_(2010)&format=json&prop=wikitext';
  const res = await fetch(url);
  if (!res.ok) throw new Error('Wikisource fetch failed: ' + res.status);
  const blob = await res.text();
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });
  writeFileSync(WIKITEXT_SRC, blob);
  return blob;
}

async function loadWikitext() {
  if (process.env.FETCH === '1' || !existsSync(WIKITEXT_SRC)) {
    console.log('▸ Fetching wikitext from Wikisource…');
    await fetchWikitext();
  }
  const raw = readFileSync(WIKITEXT_SRC, 'utf8');
  const parsed = JSON.parse(raw);
  return parsed.parse.wikitext['*'];
}

/* ───────────────────────── Text cleanup ───────────────────────── */

/** Strip wiki markup down to readable plain text. */
function clean(text) {
  let s = text;

  // Strip comments and noinclude blocks first.
  s = s.replace(/<!--[\s\S]*?-->/g, '');
  s = s.replace(/<noinclude>[\s\S]*?<\/noinclude>/gi, '');
  s = s.replace(/<includeonly>([\s\S]*?)<\/includeonly>/gi, '$1');

  // Templates. Most constitution templates are navigational; drop them.
  // But preserve {{smaller|text}} → text and {{center|text}} → text.
  s = s.replace(/\{\{(?:smaller|center|small|nowrap|lang\|\w+)\|([^}]*)\}\}/gi, '$1');
  s = s.replace(/\{\{[^{}]*?\}\}/g, '');

  // Wiki links: [[target|label]] → label, [[target]] → target
  s = s.replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, '$2');
  s = s.replace(/\[\[([^\]]+)\]\]/g, '$1');

  // External links: [http://... label] → label, [http://...] → (dropped)
  s = s.replace(/\[https?:\/\/\S+\s+([^\]]+)\]/g, '$1');
  s = s.replace(/\[https?:\/\/\S+\]/g, '');

  // Strip remaining HTML tags we do not care about.
  s = s.replace(/<br\s*\/?>/gi, ' ');
  s = s.replace(/<\/?(?:small|sub|sup|u|center|span|div|font)[^>]*>/gi, '');
  s = s.replace(/<\/?[a-z][^>]*>/gi, '');

  // Bold/italic wiki markup.
  s = s.replace(/'''''([^']+)'''''/g, '$1');
  s = s.replace(/'''([^']+)'''/g, '$1');
  s = s.replace(/''([^']+)''/g, '$1');

  // Em-dash normalisation & whitespace collapse.
  s = s.replace(/\u2013/g, '–'); // en-dash stays
  s = s.replace(/&nbsp;/gi, ' ');
  s = s.replace(/&ndash;/gi, '–');
  s = s.replace(/&mdash;/gi, '—');
  s = s.replace(/&amp;/gi, '&');
  s = s.replace(/\s+/g, ' ').trim();

  return s;
}

/* ───────────────────────── Parser ───────────────────────── */

function parseWikitext(wt) {
  const lines = wt.split('\n');
  const chapters = [];
  const schedules = [];

  let currentChapter = null;
  let currentPart = null;
  let currentArticle = null;
  /** 'main' = inside chapters; 'schedule' = inside schedules. */
  let region = 'main';
  /** Active buffer for the article we're in (or null). */

  const flushArticle = () => {
    if (!currentArticle) return;
    // Join consecutive paragraph lines that belong together.
    currentArticle.paragraphs = coalesceParagraphs(currentArticle._rawLines);
    delete currentArticle._rawLines;
    if (currentChapter) {
      currentChapter.articles.push(currentArticle);
    }
    currentArticle = null;
  };

  const startChapter = (match) => {
    flushArticle();
    // Example: "CHAPTER ONE – SOVEREIGNTY OF THE PEOPLE AND SUPREMACY OF THIS CONSTITUTION"
    const m = match.match(/^CHAPTER\s+([A-Z]+)\s*[–-]\s*(.+)$/);
    if (!m) return;
    const num = ROMAN_WORDS[m[1]];
    if (!num) return;
    currentChapter = {
      number: num,
      title: titleCase(m[2]),
      summary: '',
      articles: [],
    };
    currentPart = null;
    chapters.push(currentChapter);
  };

  const startPart = (match) => {
    flushArticle();
    // Ignore for now — parts are organisational but our schema is flat.
    currentPart = match;
  };

  const startArticle = (match) => {
    flushArticle();
    // Example: "1. Sovereignty of the people"
    const m = match.match(/^(\d+)\.\s*(.+)$/);
    if (!m) return;
    currentArticle = {
      number: parseInt(m[1], 10),
      title: clean(m[2]),
      _rawLines: [],
    };
  };

  const startSchedule = (match) => {
    flushArticle();
    region = 'schedule';
    // Example: "FIRST SCHEDULE [Article 6(1)] <br>COUNTIES"
    const m = match.match(/^(\w+)\s+SCHEDULE\s*(?:\[([^\]]+)\])?\s*(.*)$/);
    if (!m) return;
    const ord = ORDINAL_WORDS[m[1]];
    if (!ord) return;
    const sched = {
      number: ord,
      title: titleCase(clean(m[3] || '')),
      references: m[2] ? clean(m[2]) : null,
      paragraphs: [],
    };
    schedules.push(sched);
    currentChapter = null;
    currentArticle = {
      // Use a pseudo-article so our append loop works uniformly.
      _schedule: sched,
      _rawLines: [],
      number: 0,
      title: sched.title,
    };
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '');

    // Chapter heading — level 2
    let m;
    if ((m = line.match(/^==\s+(.+?)\s+==$/)) && !line.startsWith('=== ')) {
      const heading = m[1];
      if (/^CHAPTER\s/i.test(heading)) {
        region = 'main';
        startChapter(heading);
        continue;
      }
      if (/^\w+\s+SCHEDULE/i.test(heading)) {
        startSchedule(heading);
        continue;
      }
      continue; // other level-2 sections ("Main Body", etc.)
    }

    // Part heading — level 3
    if ((m = line.match(/^===\s+(.+?)\s+===$/))) {
      startPart(m[1]);
      continue;
    }

    // Article heading — level 4
    if ((m = line.match(/^====\s+(.+?)\s+====$/))) {
      if (region === 'main') {
        startArticle(m[1]);
      } else {
        // Schedule sub-heading: push as its own paragraph separator.
        if (currentArticle?._schedule) {
          currentArticle._rawLines.push({ depth: 0, text: '### ' + m[1] });
        }
      }
      continue;
    }

    // Paragraph body lines.
    if (currentArticle) {
      // Indent depth: count leading colons.
      const colonMatch = line.match(/^(:+)(.*)$/);
      if (colonMatch) {
        currentArticle._rawLines.push({
          depth: colonMatch[1].length,
          text: colonMatch[2].trimStart(),
        });
      } else if (line.trim() === '') {
        currentArticle._rawLines.push({ depth: 0, text: '' });
      } else if (!line.startsWith('<pages ') && !line.startsWith('{{ppb')) {
        // Fallback: preserve the line at depth 0.
        currentArticle._rawLines.push({ depth: 0, text: line });
      }
    }
  }

  flushArticle();

  // Schedules capture: move their pseudo-articles into the schedule itself.
  for (const sched of schedules) {
    sched.paragraphs = [];
  }
  // Second pass over lines wouldn't help; we already collected schedule body
  // into a pseudo-article that got pushed onto a (now-empty) currentChapter.
  // Re-walk: simpler to re-parse schedule bodies in a follow-up call.

  return { chapters, schedules };
}

/**
 * Turn the indented raw lines of an article into our paragraphs[] array.
 *
 * Rule of thumb: each top-level clause ("(1) …", "(2) …") starts a new
 * paragraph, but its sub-clauses ((a), (b), (i), (ii)) are joined into
 * the same paragraph separated by spaces. This matches the formatting
 * we use in the hand-authored chapters.
 */
function coalesceParagraphs(rawLines) {
  const out = [];
  let buf = '';

  const flush = () => {
    const t = clean(buf);
    if (t.length > 0) out.push(t);
    buf = '';
  };

  for (const { depth, text } of rawLines) {
    const stripped = text.trim();
    if (!stripped) {
      flush();
      continue;
    }
    // Top-level clause starter — depth 1 with "(N)" at the start.
    const startsNewClause =
      depth === 1 && /^\(\d+[A-Za-z]?\)/.test(stripped);
    if (startsNewClause) {
      flush();
      buf = stripped;
    } else if (buf.length > 0) {
      buf += ' ' + stripped;
    } else {
      buf = stripped;
    }
  }
  flush();
  return out;
}

function titleCase(s) {
  const small = new Set([
    'a', 'an', 'and', 'as', 'at', 'by', 'for', 'in', 'of', 'on',
    'or', 'the', 'to', 'with', 'from',
  ]);
  return clean(s)
    .toLowerCase()
    .split(/\s+/)
    .map((w, i) => {
      if (i > 0 && small.has(w)) return w;
      // Preserve hyphenated words.
      return w
        .split('-')
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join('-');
    })
    .join(' ');
}

/* ───────────────────────── Editorial merge ───────────────────────── */

const EDITORIAL_FIELDS = ['label', 'summary', 'explanation', 'tags'];

function mergeWithExisting(parsedChapter) {
  const target = join(DATA_DIR, `chapter-${parsedChapter.number}.json`);
  if (!existsSync(target)) return parsedChapter;
  try {
    const existing = JSON.parse(readFileSync(target, 'utf8'));
    // Keep the existing chapter summary if present.
    if (existing.summary && existing.summary.length > 0) {
      parsedChapter.summary = existing.summary;
    }
    const existingArticles = new Map();
    for (const a of existing.articles || []) {
      existingArticles.set(a.number, a);
    }
    for (const art of parsedChapter.articles) {
      const prev = existingArticles.get(art.number);
      if (!prev) continue;
      for (const field of EDITORIAL_FIELDS) {
        if (prev[field] !== undefined) art[field] = prev[field];
      }
    }
  } catch {
    // fall through — write a fresh file
  }
  return parsedChapter;
}

/* ───────────────────────── Schedules body extraction ───────────────────────── */

/**
 * Second, simpler pass to extract schedule content. Returns the schedules
 * array fully populated with paragraphs.
 */
function extractSchedules(wt) {
  const lines = wt.split('\n');
  const out = [];
  let current = null;
  let inSchedule = false;
  let raw = [];

  const flush = () => {
    if (!current) return;
    current.paragraphs = coalesceParagraphs(raw);
    out.push(current);
    current = null;
    raw = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '');
    let m;
    if ((m = line.match(/^==\s+(\w+)\s+SCHEDULE\s*(?:\[([^\]]+)\])?\s*(.*?)\s+==$/))) {
      flush();
      const ord = ORDINAL_WORDS[m[1].toUpperCase()];
      if (!ord) {
        inSchedule = false;
        continue;
      }
      current = {
        number: ord,
        title: titleCase(clean(m[3] || m[1] + ' Schedule')),
        references: m[2] ? clean(m[2]) : null,
        paragraphs: [],
      };
      inSchedule = true;
      raw = [];
      continue;
    }
    // End of schedules region: level 2 heading that's not a schedule.
    if (line.match(/^==\s+[^=]+\s+==$/) && !line.includes('SCHEDULE')) {
      flush();
      inSchedule = false;
      continue;
    }
    if (!inSchedule) continue;
    if (line.match(/^={3,5}\s+(.+?)\s+={3,5}$/)) {
      raw.push({ depth: 0, text: line.replace(/^=+\s+/, '').replace(/\s+=+$/, '') });
      continue;
    }
    const colonMatch = line.match(/^(:+)(.*)$/);
    if (colonMatch) {
      raw.push({ depth: colonMatch[1].length, text: colonMatch[2].trimStart() });
    } else if (line.trim() === '') {
      raw.push({ depth: 0, text: '' });
    } else if (!line.startsWith('<pages') && !line.startsWith('{{')) {
      raw.push({ depth: 0, text: line });
    }
  }
  flush();
  return out;
}

/* ───────────────────────── Chapter summary fallback ───────────────────────── */

const CHAPTER_FALLBACK_SUMMARY = {
  4: 'The Bill of Rights — every fundamental freedom the state must protect, from life and dignity to housing, healthcare, and fair labour.',
  5: 'How land is held, used and protected, and the principles governing Kenya\'s environment and natural resources.',
  7: 'Elections and the rules of political representation — including the electoral system, IEBC, and political parties.',
  8: 'Parliament: the National Assembly and the Senate, how they are composed, elected and how laws are passed.',
  9: 'The national executive: the President, Deputy President, Cabinet, and the Attorney-General — and the limits on their power.',
  10: 'The Judiciary — how Kenya\'s courts are structured, who appoints judges, and how judicial independence is protected.',
  13: 'The Public Service: values, principles, and the commissions that hire, oversee, and discipline public servants.',
  14: 'National security: the defence forces, intelligence service, police service, and the civilian oversight of each.',
  15: 'The constitutional commissions and independent offices — watchdogs designed to survive changes of government.',
  16: 'How this Constitution itself can be amended — by parliamentary supermajority or by referendum.',
  17: 'General provisions — definitions, authoritative versions, and the interpretation rules that bind the whole document.',
  18: 'Transitional rules — how the 2010 Constitution replaced the old order, and a timeline for enacting the laws it requires.',
};

/* ───────────────────────── Main ───────────────────────── */

(async () => {
  const wt = await loadWikitext();
  const { chapters } = parseWikitext(wt);
  const schedules = extractSchedules(wt);

  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
  if (!existsSync(CACHE_DIR)) mkdirSync(CACHE_DIR, { recursive: true });

  const writtenMeta = [];
  for (const ch of chapters) {
    if (!ch.summary) ch.summary = CHAPTER_FALLBACK_SUMMARY[ch.number] ?? '';
    const merged = mergeWithExisting(ch);
    const out = join(DATA_DIR, `chapter-${ch.number}.json`);
    writeFileSync(out, JSON.stringify(merged, null, 2) + '\n');
    writtenMeta.push({
      number: ch.number,
      title: ch.title,
      summary: ch.summary,
      articleRange: [
        merged.articles[0]?.number ?? 0,
        merged.articles[merged.articles.length - 1]?.number ?? 0,
      ],
      articles: merged.articles.length,
      articleTitles: merged.articles.map((a) => ({ number: a.number, title: a.title })),
      dataPath: `/data/constitution/chapter-${ch.number}.json`,
    });
    console.log(
      `  ✓ chapter-${ch.number}.json  — ${merged.articles.length} articles (${ch.title})`
    );
  }

  writeFileSync(
    join(DATA_DIR, 'schedules.json'),
    JSON.stringify({ schedules }, null, 2) + '\n'
  );
  console.log(`  ✓ schedules.json — ${schedules.length} schedules`);

  writeFileSync(META_OUT, JSON.stringify({ chapters: writtenMeta }, null, 2) + '\n');
  console.log(`  ✓ .cache/constitution-meta.json — for pasting into index.ts`);

  const total = chapters.reduce((s, c) => s + c.articles.length, 0);
  console.log(`\nDone: ${chapters.length} chapters, ${total} articles.`);
})();
