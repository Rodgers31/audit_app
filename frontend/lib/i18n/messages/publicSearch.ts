export const PUBLIC_SEARCH_MESSAGES = {
  label: { en: 'Search AuditGava', sw: 'Tafuta kwenye AuditGava', plain: 'Search AuditGava' },
  help: {
    en: 'Search counties, Constitution articles and glossary terms.',
    sw: 'Tafuta kaunti, ibara za Katiba na istilahi.',
    plain: 'Look up a county, an article of the Constitution or a glossary term.',
  },
  clear: { en: 'Clear search', sw: 'Futa utafutaji', plain: 'Clear search' },
  counties: { en: 'Counties', sw: 'Kaunti', plain: 'Counties' },
  articles: { en: 'Constitution articles', sw: 'Ibara za Katiba', plain: 'Constitution articles' },
  glossary: { en: 'Glossary terms', sw: 'Istilahi', plain: 'Glossary terms' },
  article: { en: 'Article {number}', sw: 'Ibara ya {number}', plain: 'Article {number}' },
  short: {
    en: 'Enter at least three characters or an article number.',
    sw: 'Andika angalau herufi tatu au nambari ya ibara.',
    plain: 'Type three or more characters or an article number.',
  },
  loading: {
    en: 'Searching Constitution articles…',
    sw: 'Inatafuta ibara za Katiba…',
    plain: 'Searching Constitution articles…',
  },
  empty: {
    en: 'No matching counties, articles or glossary terms.',
    sw: 'Hakuna kaunti, ibara au istilahi zinazolingana.',
    plain: 'No counties, articles or glossary terms match your search.',
  },
  one: { en: 'One result shown.', sw: 'Tokeo moja limeonyeshwa.', plain: 'One result shown.' },
  many: { en: '{count} results shown.', sw: 'Matokeo {count} yameonyeshwa.', plain: '{count} results shown.' },
  partial: {
    en: 'Some Constitution article text is unavailable.',
    sw: 'Maandishi ya baadhi ya ibara za Katiba hayapatikani.',
    plain: 'We could only search some Constitution articles.',
  },
  unavailable: {
    en: 'Constitution article search is unavailable. Try an article number.',
    sw: 'Utafutaji wa ibara za Katiba haupatikani. Jaribu nambari ya ibara.',
    plain: 'We could not search the Constitution text. Try an article number.',
  },
} as const;
