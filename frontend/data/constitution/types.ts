/**
 * Constitution of Kenya — data contracts.
 *
 * The Constitution is split across chapter JSON files served from
 * /public/data/constitution/chapter-<n>.json. This module defines the
 * types those files adhere to and a lightweight index for O(1) lookup
 * without paying the cost of loading full chapter bodies upfront.
 */

export interface ConstitutionArticle {
  /** Article number — unique across the whole Constitution. */
  number: number;
  /** Optional subsection label (e.g. "Article 2" vs "Article 2(5)"). */
  label?: string;
  /** Short article title. */
  title: string;
  /**
   * The article body — a list of paragraphs. Keeping it as an array
   * lets the viewer render each clause as a separate block and makes
   * search highlighting predictable.
   */
  paragraphs: string[];
  /** Optional plain-English summary for readers who want the gist. */
  summary?: string;
  /** Optional "why it matters" callout linking back to real-world impact. */
  explanation?: string;
  /** Tags for cross-linking (e.g. "auditor-general", "devolution"). */
  tags?: string[];
}

export interface ConstitutionChapter {
  /** Chapter number (1-18 in Kenya's 2010 Constitution). */
  number: number;
  /** Short chapter title. */
  title: string;
  /** One-sentence chapter summary shown in the sidebar and cards. */
  summary: string;
  /** Article list, kept in canonical order. */
  articles: ConstitutionArticle[];
}

/** Lightweight index entry — shipped in the initial JS bundle. */
export interface ChapterMeta {
  number: number;
  title: string;
  summary: string;
  /** Article numbers covered — used for search-by-number routing. */
  articleRange: [number, number];
  /** Article titles only — enough for sidebar + keyword preview. */
  articleTitles: Array<{ number: number; title: string }>;
  /** Path under /public for lazy fetching of the full chapter body. */
  dataPath: string;
  /** Optional highlight callout for the hub cards. */
  highlight?: string;
}
