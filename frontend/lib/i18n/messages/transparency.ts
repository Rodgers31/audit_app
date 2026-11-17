export const countySpendingMessages = {
  title: {
    en: 'County spending', sw: 'Matumizi ya kaunti', plain: 'County spending',
  },
  fiscalYear: {
    en: 'FY {year}', sw: 'Mwaka wa fedha {year}', plain: 'Financial year {year}',
  },
  allocationCoverage: {
    en: '{count} of 47 counties have published allocations',
    sw: 'Kaunti {count} kati ya 47 zimechapisha mgao wa bajeti',
    plain: '{count} of 47 counties have published how much they were given',
  },
  allocationCoverageProjected: {
    en: 'Allocation figures are available for {count} of 47 counties',
    sw: 'Takwimu za mgao zinapatikana kwa kaunti {count} kati ya 47',
    plain: 'We have allocation figures for {count} of 47 counties',
  },
  search: {
    en: 'Find your county', sw: 'Tafuta kaunti yako', plain: 'Find your county',
  },
  clearSearch: {
    en: 'Clear county search', sw: 'Futa utafutaji wa kaunti', plain: 'Clear county search',
  },
  sort: { en: 'Sort by', sw: 'Panga kwa', plain: 'Sort by' },
  reverse: { en: 'Reverse sort order', sw: 'Geuza mpangilio', plain: 'Reverse the order' },
  efficiency: { en: 'Least spent first', sw: 'Asilimia ndogo kwanza', plain: 'Lowest share spent first' },
  gap: { en: 'Biggest gap', sw: 'Pengo kubwa zaidi', plain: 'Most money unspent' },
  name: { en: 'A–Z', sw: 'A–Z', plain: 'A–Z' },
  flagged: { en: 'Most questioned', sw: 'Kiasi kikubwa kilichohojiwa', plain: 'Most money questioned' },
  allocated: { en: 'Largest allocation', sw: 'Mgao mkubwa zaidi', plain: 'Most money given' },
  below65: { en: 'Under 65%', sw: 'Chini ya 65%', plain: 'Under 65%' },
  below70: { en: '65–69%', sw: '65–69%', plain: '65–69%' },
  below80: { en: '70–79%', sw: '70–79%', plain: '70–79%' },
  atLeast80: { en: '80%+', sw: '80% na zaidi', plain: '80% or more' },
  target: { en: '{target}% target', sw: 'Lengo la {target}%', plain: '{target}% target' },
  markers: {
    en: 'Short tick: {target}% target. Long tick: national share spent ({national}%).',
    sw: 'Alama fupi: lengo la {target}%. Alama ndefu: asilimia iliyotumika nchini ({national}%).',
    plain: 'Short mark: {target}% target. Long mark: share spent across Kenya ({national}%).',
  },
  efficiencyBar: {
    en: '{county}: {spent}% of allocation spent. Target: {target}%.',
    sw: '{county}: {spent}% ya mgao imetumika. Lengo: {target}%.',
    plain: '{county}: spent {spent}% of the money it was given. Target: {target}%.',
  },
  nationalBar: {
    en: '{county}: {spent}% of allocation spent. Target: {target}%. National share spent: {national}%.',
    sw: '{county}: {spent}% ya mgao imetumika. Lengo: {target}%. Asilimia iliyotumika nchini: {national}%.',
    plain: '{county}: spent {spent}% of the money it was given. Target: {target}%. Share spent across Kenya: {national}%.',
  },
  targetMarker: {
    en: 'Marker shows the {target}% target.',
    sw: 'Alama inaonyesha lengo la {target}%.',
    plain: 'The mark shows the {target}% target.',
  },
  auditMissing: {
    en: 'Audit amounts are unavailable for {period} (shown as —).',
    sw: 'Kiasi cha ukaguzi hakipatikani kwa {period} (alama —).',
    plain: 'We don’t have audit amounts for {period} (shown as —).',
  },
  auditContext: {
    en: 'Questioned amounts are discussed in audit reports. They do not measure proven loss or theft. A dash means the amount is unavailable.',
    sw: 'Kiasi kilichohojiwa kinajadiliwa kwenye ripoti za ukaguzi. Hakionyeshi hasara au wizi uliothibitishwa. Kistari kinaonyesha kiasi hakipatikani.',
    plain: 'Auditors raised questions about these amounts. That does not mean the money was proven lost or stolen. A dash means the amount is unavailable.',
  },
  oneCounty: { en: '1 county', sw: 'Kaunti 1', plain: '1 county' },
  countyCount: { en: '{count} counties', sw: 'Kaunti {count}', plain: '{count} counties' },
  orderedBy: {
    en: 'Counties ordered by {sort}', sw: 'Kaunti zimepangwa kwa {sort}', plain: 'Counties ordered by {sort}',
  },
  reversedOrder: {
    en: 'Counties ordered by {sort}, reversed',
    sw: 'Kaunti zimepangwa kwa {sort}, kinyume',
    plain: 'Counties ordered by {sort}, in reverse',
  },
  showAll: {
    en: 'Show all {count} counties', sw: 'Onyesha kaunti zote {count}', plain: 'Show all {count} counties',
  },
  loading: {
    en: 'Loading county data…', sw: 'Inapakia data za kaunti…', plain: 'Loading county data…',
  },
  error: {
    en: 'County data could not be loaded. Please try again.',
    sw: 'Data za kaunti hazikupakiwa. Jaribu tena.',
    plain: 'We couldn’t load the county data. Please try again.',
  },
  noMatch: {
    en: 'No counties match your search.', sw: 'Hakuna kaunti inayolingana na utafutaji wako.',
    plain: 'No counties match your search.',
  },
  noData: {
    en: 'No data available for this fiscal year.',
    sw: 'Hakuna data ya mwaka huu wa fedha.',
    plain: 'No data is available for this financial year.',
  },
  allocation: {
    en: '{amount} allocated', sw: 'Mgao wa {amount}', plain: '{amount} given',
  },
  allocationShare: {
    en: 'of national allocation', sw: 'ya mgao wa kitaifa', plain: 'of the total given to counties',
  },
  pending: {
    en: 'Execution pending', sw: 'Takwimu za matumizi bado hazijapatikana', plain: 'Spending figures pending',
  },
  unreported: {
    en: 'Spending share unavailable', sw: 'Asilimia iliyotumika haipatikani', plain: 'Share spent unavailable',
  },
  spent: { en: 'Spent', sw: 'Kilichotumika', plain: 'Spent' },
  unspent: { en: 'Gap', sw: 'Pengo', plain: 'Unspent' },
  auditFlagged: { en: 'Flagged', sw: 'Kilichoashiriwa', plain: 'Flagged' },
  auditQuestioned: { en: 'Questioned', sw: 'Kilichohojiwa', plain: 'Questioned' },
  auditAmountUnavailable: {
    en: 'Audit amount unavailable', sw: 'Kiasi cha ukaguzi hakipatikani', plain: 'Audit amount unavailable',
  },
  unavailable: { en: 'Unavailable', sw: 'Hakipatikani', plain: 'Unavailable' },
  wellBelow: {
    en: 'Well below target', sw: 'Mbali chini ya lengo', plain: 'Well below target',
  },
  below: { en: 'Below target', sw: 'Chini ya lengo', plain: 'Below target' },
  onTarget: { en: 'On target', sw: 'Limelenga shabaha', plain: 'On target' },
  above: { en: 'Above target', sw: 'Juu ya lengo', plain: 'Above target' },
} as const;

export const nationalSpendingMessages = {
  subtitle: {
    en: 'See what counties were allocated, what they spent and what auditors questioned.',
    sw: 'Angalia mgao wa kaunti, matumizi yao na kiasi kilichohojiwa na wakaguzi.',
    plain: 'See how much money counties were given, how much they spent and what auditors questioned.',
  },
  period: {
    en: 'Counties · FY {year}', sw: 'Kaunti · Mwaka wa fedha {year}', plain: 'Counties · Financial year {year}',
  },
  verdict: {
    en: 'Counties spent {percent}',
    sw: 'Kaunti zilitumia {percent}',
    plain: 'Counties spent {percent}',
  },
  comparison: {
    en: 'of their allocation ({spent} of {allocated}).',
    sw: 'ya mgao wao ({spent} kati ya {allocated}).',
    plain: 'of the money they were given ({spent} out of {allocated}).',
  },
  spentSegment: {
    en: 'Spent {amount}', sw: 'Imetumika {amount}', plain: 'Spent {amount}',
  },
  remaining: {
    en: '{amount} not yet spent at the time of the report.',
    sw: '{amount} zilikuwa bado hazijatumika wakati wa ripoti.',
    plain: '{amount} was still unspent when the report was written.',
  },
  overspend: {
    en: 'Reported spending exceeded the allocation by {amount}.',
    sw: 'Matumizi yaliyoripotiwa yalizidi mgao kwa {amount}.',
    plain: 'Counties spent {amount} more than they were given.',
  },
  loading: {
    en: 'Loading national spending…',
    sw: 'Inapakia matumizi ya kitaifa…',
    plain: 'Loading spending for all counties…',
  },
  error: {
    en: 'National spending could not be loaded.',
    sw: 'Takwimu za matumizi ya kitaifa hazikupakiwa.',
    plain: 'We couldn’t load spending for all counties.',
  },
  retry: {
    en: 'Try again', sw: 'Jaribu tena', plain: 'Try again',
  },
  reported: {
    en: 'National spending figures', sw: 'Takwimu za matumizi ya kitaifa', plain: 'Spending figures for all counties',
  },
  unavailable: {
    en: 'National spending figures unavailable',
    sw: 'Takwimu za matumizi ya kitaifa hazipatikani',
    plain: 'Spending figures for all counties are unavailable',
  },
  noComparison: {
    en: 'A comparison from one published report is unavailable for this period.',
    sw: 'Ulinganisho kutoka ripoti moja iliyochapishwa haupatikani kwa kipindi hiki.',
    plain: 'We don’t have one published report that supports a comparison for this period.',
  },
  allocationUnavailable: {
    en: 'The national allocation is unavailable for this period.',
    sw: 'Mgao wa kitaifa haupatikani kwa kipindi hiki.',
    plain: 'We don’t have the total amount counties were given for this period.',
  },
  spendingUnavailable: {
    en: 'Reported spending is unavailable for this period.',
    sw: 'Matumizi yaliyoripotiwa hayapatikani kwa kipindi hiki.',
    plain: 'We don’t have a published spending figure for this period.',
  },
  zeroAllocation: {
    en: 'A spending percentage requires a positive allocation.',
    sw: 'Asilimia ya matumizi huhitaji mgao ulio zaidi ya sifuri.',
    plain: 'We need an allocation above zero to calculate the share spent.',
  },
  allocation: {
    en: 'Reported allocation', sw: 'Mgao ulioripotiwa', plain: 'Amount given',
  },
  spending: {
    en: 'Reported spending', sw: 'Matumizi yaliyoripotiwa', plain: 'Amount spent',
  },
  estimate: {
    en: 'Modelled allocation', sw: 'Makadirio ya mgao', plain: 'Estimated allocation',
  },
  mixedAllocation: {
    en: 'Reported and modelled allocation',
    sw: 'Mgao ulioripotiwa na uliokadiriwa',
    plain: 'Published and estimated allocation',
  },
  projected: {
    en: 'Modelled county allocation',
    sw: 'Makadirio ya mgao wa kaunti',
    plain: 'Estimated allocation for all counties',
  },
  source: {
    en: 'Source and method', sw: 'Chanzo na mbinu', plain: 'Where the figures come from',
  },
  reportLink: {
    en: 'Controller of Budget county implementation report',
    sw: 'Ripoti ya Mdhibiti wa Bajeti kuhusu utekelezaji wa bajeti za kaunti',
    plain: 'Controller of Budget report on county spending',
  },
  method: {
    en: 'Allocation and expenditure use the county budget totals in this report. Any unspent amount is the difference between those totals at the time of the report.',
    sw: 'Mgao na matumizi yanatumia jumla za bajeti za kaunti katika ripoti hii. Kiasi ambacho hakijatumika ni tofauti ya jumla hizo wakati wa ripoti.',
    plain: 'We use the totals from this report for both figures. Any money still unspent is the difference between what counties were given and what they spent by the time of the report.',
  },
  cob: {
    en: 'The allocation uses county budget figures from the Controller of Budget.',
    sw: 'Mgao huu umetokana na takwimu za bajeti za kaunti kutoka kwa Mdhibiti wa Bajeti.',
    plain: 'The allocation uses county budget figures from the Controller of Budget.',
  },
  craModel: {
    en: 'The allocation is estimated using the Commission on Revenue Allocation’s equitable-share formula.',
    sw: 'Mgao umekadiriwa kwa kutumia fomula ya mgao sawa ya Tume ya Ugawaji wa Mapato.',
    plain: 'The estimate uses the Commission on Revenue Allocation’s formula for sharing revenue.',
  },
  mixed: {
    en: 'The allocation combines Controller of Budget figures with Commission on Revenue Allocation estimates.',
    sw: 'Mgao unajumuisha takwimu za Mdhibiti wa Bajeti na makadirio ya Tume ya Ugawaji wa Mapato.',
    plain: 'The allocation combines published figures from the Controller of Budget with estimates from the Commission on Revenue Allocation.',
  },
} as const;
