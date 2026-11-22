import type { FindingsListData } from '@/lib/api/audits';
import type { NationalLoansResponse } from '@/lib/api/debt';
import { displayLenderName } from '@/lib/debt/lenderName';
import { evidenceUrl } from '@/lib/evidence/qualification';

export const AUDIT_SEARCH_LIMIT = 100;
const RESULT_LIMIT = 5;
const LENDER_NAME_LIMIT = 200;
const WORD_SEPARATORS = new RegExp('[\\s\\p{P}]+', 'gu');

interface AuditResult {
  key: number;
  href: string;
  title: string;
  context: string;
}

function searchText(value: string) {
  return value.normalize('NFKC').toLocaleLowerCase('en-KE').replace(WORD_SEPARATORS, ' ').trim();
}

function text(value: string | null | undefined) {
  return typeof value === 'string' ? value.replace(/\s+/g, ' ').trim() : '';
}

// A named locator or a document-level URL cannot open the cited PDF page.
// Match the API's numeric locator and check against the URL it supplied.
function reportPageHref(url: string | null, pageRef: string | null | undefined) {
  const href = evidenceUrl(url);
  const locator = text(pageRef).match(/^(?:(?:pp?\.?|pages?)\s*)?([0-9]{1,9})(?:\s*[-–]\s*([0-9]{1,9}))?$/i);
  if (!href || !locator) return undefined;
  const page = Number(locator[1]);
  if (page < 1 || (locator[2] && Number(locator[2]) < page)) return undefined;
  const target = new URL(href);
  const pages = new URLSearchParams(target.hash.slice(1)).getAll('page');
  if (target.pathname.toLowerCase().endsWith('.pdf') && pages.length === 1 && pages[0] === String(page)) {
    return href;
  }
}

export function findPublishedAuditResults(data: FindingsListData, query: string): AuditResult[] {
  const match = searchText(query);
  if (!match) return [];
  const headings: AuditResult[] = [];
  const excerpts: AuditResult[] = [];
  for (const item of data.items.slice(0, AUDIT_SEARCH_LIMIT)) {
    const title = text(item.finding_title);
    const finding = text(item.finding_text);
    const context = text(item.audited_entity_name) || text(item.county_name);
    const headingMatch = searchText(title).includes(match);
    if (!headingMatch && !searchText(finding).includes(match) && !searchText(context).includes(match)) continue;

    const href = reportPageHref(item.source_document_url, item.page_ref);
    if (!href || (!title && !finding)) continue;
    const excerpt = finding.length > 150
      ? `${finding.slice(0, 150).replace(/\s+\S*$/, '')}…`
      : finding;
    (headingMatch ? headings : excerpts).push({ key: item.id, href, title: title || excerpt, context });
  }
  return [...headings, ...excerpts].slice(0, RESULT_LIMIT);
}

export function readLenderQuery(values: string[]) {
  const [value] = values;
  if (values.length !== 1 || Array.from(value).length > LENDER_NAME_LIMIT || /[\x00-\x1f\x7f-\x9f]/.test(value)) return '';
  return displayLenderName(value);
}

export function findPublishedLenderResults(data: NationalLoansResponse, query: string) {
  const match = searchText(query);
  if (!match) return [];
  const matches = new Map<string, { title: string; href: string; rank: number }>();
  for (const loan of data.loans) {
    const title = displayLenderName(loan.lender);
    if (!title || !readLenderQuery([title])) continue;
    const key = title.toLocaleLowerCase('en-KE');
    const name = searchText(title);
    if (!name.includes(match) || matches.has(key)) continue;

    const rank = name === match ? 0 : name.startsWith(match) ? 1 : 2;
    const queryString = new URLSearchParams({ lender: title }).toString();
    matches.set(key, { title, href: `/debt?${queryString}#loan-register`, rank });
  }
  return Array.from(matches.values())
    .sort((a, b) => a.rank - b.rank || a.title.localeCompare(b.title, 'en-KE'))
    .slice(0, RESULT_LIMIT);
}
