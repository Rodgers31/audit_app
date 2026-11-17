import type { Lang, Translation } from '../messages';

const LEARN_MESSAGES = {
  search: { en: 'Search', sw: 'Tafuta', plain: 'Search' },
  readerSearch: { en: 'Search the reader', sw: 'Tafuta katika kisomaji', plain: 'Search the reader' },
  readerSearchLabel: { en: 'Search Constitution articles', sw: 'Tafuta vifungu vya Katiba', plain: 'Search Constitution articles' },
  readerSearchPlaceholder: { en: 'Public debt or Article 214', sw: 'Mfano: public debt au 214', plain: 'Public debt or Article 214' },
  readerSearchHelp: { en: 'Search the English text or enter an article number.', sw: 'Tafuta katika maandishi ya Kiingereza au andika nambari ya kifungu.', plain: 'Type an English term or an article number.' },
  readerSearchLoading: { en: 'Searching articles…', sw: 'Inatafuta vifungu…', plain: 'Searching articles…' },
  readerSearchClear: { en: 'Clear article search', sw: 'Futa utafutaji wa vifungu', plain: 'Clear article search' },
  readerSearchShort: { en: 'Enter at least three characters or an article number.', sw: 'Andika angalau herufi tatu au nambari ya kifungu.', plain: 'Type three or more characters or an article number.' },
  readerSearchEmpty: { en: 'No matching articles.', sw: 'Hakuna vifungu vinavyolingana.', plain: 'No matching articles.' },
  readerSearchError: { en: 'Search could not load. Try an article number.', sw: 'Utafutaji haukupakiwa. Jaribu nambari ya kifungu.', plain: 'Search could not load. Try an article number.' },
  readerSearchResult: { en: '1 matching article', sw: 'Kifungu 1 kinacholingana', plain: '1 matching article' },
  readerSearchResults: { en: 'Showing {count} matching articles', sw: 'Inaonyesha vifungu {count} vinavyolingana', plain: 'Showing {count} matching articles' },
  readerSearchChapter: { en: 'Chapter {chapter}', sw: 'Sura ya {chapter}', plain: 'Chapter {chapter}' },
  chapters: { en: 'Chapters', sw: 'Sura', plain: 'Chapters' },
  readerTitle: { en: 'Constitution of Kenya reader', sw: 'Kisomaji cha Katiba ya Kenya', plain: 'Read the Constitution of Kenya' },
  bookHeading: { en: 'Read the law that shapes every shilling', sw: 'Soma sheria inayoongoza matumizi ya kila shilingi', plain: 'Read the law that shapes every shilling' },
  bookCoverage: { en: '{chapters} chapters, {articles} articles', sw: 'Sura {chapters}, vifungu {articles}', plain: '{chapters} chapters, {articles} articles' },
  textVersion: { en: 'Text version', sw: 'Aina ya maandishi', plain: 'Text version' },
  plainEnglish: { en: 'Plain English', sw: 'Kiingereza rahisi', plain: 'Plain English' },
  plainUnavailable: { en: 'A plain-English summary is unavailable for this article.', sw: 'Muhtasari wa kifungu hiki kwa Kiingereza rahisi haupatikani.', plain: 'This article has no plain-English summary yet.' },
  officialText: { en: 'Official text', sw: 'Maandishi rasmi', plain: 'Official text' },
  transcript: { en: 'Reader transcription from Wikisource.', sw: 'Nakala ya kusomea imetokana na Wikisource.', plain: 'Transcribed from Wikisource.' },
  source: { en: 'Authoritative text from Kenya Law (National Council for Law Reporting)', sw: 'Maandishi rasmi kutoka Kenya Law (Baraza la Kitaifa la Kuripoti Sheria)', plain: 'Authoritative text from Kenya Law (National Council for Law Reporting)' },
  chapterTitle: { en: 'Ch. {chapter} · {title}', sw: 'Sura ya {chapter} · {title}', plain: 'Ch. {chapter} · {title}' },
  chapterProgress: { en: '{count} articles left in Chapter {chapter}', sw: 'Vifungu {count} vimebaki katika Sura ya {chapter}', plain: '{count} articles left in Chapter {chapter}' },
  chapterProgressOne: { en: '1 article left in Chapter {chapter}', sw: 'Kifungu 1 kimebaki katika Sura ya {chapter}', plain: '1 article left in Chapter {chapter}' },
  article: { en: 'Art. {number}', sw: 'Kif. {number}', plain: 'Art. {number}' },
  articleRange: { en: 'Articles {first}–{last}', sw: 'Vifungu {first}–{last}', plain: 'Articles {first}–{last}' },
  backTo: { en: 'Back to Article {number}', sw: 'Rudi kwenye Kifungu cha {number}', plain: 'Back to Article {number}' },
  loading: { en: 'Loading chapter…', sw: 'Inapakia sura…', plain: 'Loading chapter…' },
  loadError: { en: 'Could not load Chapter {chapter}. Please try another chapter.', sw: 'Sura ya {chapter} haikupakiwa. Jaribu sura nyingine.', plain: 'Chapter {chapter} could not load. Try another chapter.' },
  where: { en: 'Where this shows up on AuditGava', sw: 'Mahali jambo hili linapoonekana kwenye AuditGava', plain: 'Where this shows up on AuditGava' },
  budget: { en: 'Budget', sw: 'Bajeti', plain: 'Budget' },
  countyMoney: { en: 'County money', sw: 'Fedha za kaunti', plain: 'County money' },
  debt: { en: 'National debt', sw: 'Deni la taifa', plain: 'National debt' },
  audits: { en: 'Audit findings', sw: 'Matokeo ya ukaguzi', plain: 'Audit findings' },
  countyAudits: { en: 'Find your county’s audit record', sw: 'Pata rekodi za ukaguzi za kaunti yako', plain: 'Find your county’s audit record' },
  why: { en: 'Why it matters', sw: 'Kwa nini ni muhimu', plain: 'Why it matters' },
} satisfies Record<string, Translation>;

export function learnCopy(
  lang: Lang,
  key: keyof typeof LEARN_MESSAGES,
  values: Record<string, string | number> = {},
): string {
  return LEARN_MESSAGES[key][lang].replace(/\{(\w+)\}/g, (placeholder, name: string) =>
    String(values[name] ?? placeholder)
  );
}
