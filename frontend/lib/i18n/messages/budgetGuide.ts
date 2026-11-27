export const BUDGET_GUIDE_MESSAGES = {
  paths: { en: 'Guided paths', sw: 'Masomo ya hatua kwa hatua', plain: 'Guided paths' },
  title: {
    en: 'Understand this year’s budget in 5 minutes',
    sw: 'Elewa bajeti ya mwaka huu kwa dakika 5',
    plain: 'Understand this year’s budget in 5 minutes',
  },
  metadataDescription: {
    en: 'A guided path through Kenya’s approved budget expenditure, revenue, financing and county transfers.',
    sw: 'Mwongozo wa matumizi, mapato, ufadhili na uhamisho kwa kaunti katika bajeti iliyoidhinishwa ya Kenya.',
    plain: 'Learn what Kenya plans to spend, where the money comes from, how it covers the gap and what goes to counties.',
  },
  progress: { en: 'Step {step} of {total}', sw: 'Hatua ya {step} kati ya {total}', plain: 'Step {step} of {total}' },
  approved: { en: 'Approved fiscal framework · {year}', sw: 'Mfumo wa fedha ulioidhinishwa · {year}', plain: 'Approved budget plan · {year}' },
  amount: { en: 'KES {number} billion', sw: 'KSh bilioni {number}', plain: 'KES {number} billion' },
  loading: { en: 'Loading the current budget figure…', sw: 'Inapakia takwimu ya bajeti ya sasa…', plain: 'Loading the current budget figure…' },
  loadError: { en: 'The current budget figure could not be loaded.', sw: 'Takwimu ya bajeti ya sasa haikuweza kupakiwa.', plain: 'We could not load the current budget figure.' },
  yearUnavailable: { en: 'Figures for the current fiscal year, {year}, are unavailable.', sw: 'Takwimu za mwaka wa fedha wa sasa, {year}, hazipatikani.', plain: 'The figures for this budget year, {year}, are unavailable.' },
  figureUnavailable: { en: 'An approved figure with a verified source is unavailable for {year}.', sw: 'Takwimu iliyoidhinishwa yenye chanzo kilichothibitishwa haipatikani kwa {year}.', plain: 'We do not have a checked source for this approved figure for {year}.' },
  retry: { en: 'Try again', sw: 'Jaribu tena', plain: 'Try again' },
  previous: { en: 'Previous', sw: 'Iliyotangulia', plain: 'Previous' },
  next: { en: 'Next', sw: 'Inayofuata', plain: 'Next' },
  back: { en: 'Back to guided paths', sw: 'Rudi kwenye masomo ya hatua kwa hatua', plain: 'Back to guided paths' },
} as const;

export const BUDGET_GUIDE_STEP_COPY = {
  spending: {
    title: { en: 'What the government plans to spend', sw: 'Matumizi yaliyopangwa na serikali', plain: 'What the government plans to spend' },
    description: {
      en: 'Use the Treasury’s expenditure and net lending figure to read planned recurrent spending, development, county transfers and contingency on the same basis.',
      sw: 'Tumia takwimu ya Hazina ya matumizi na mikopo halisi kusoma matumizi ya kawaida, maendeleo, uhamisho kwa kaunti na akiba ya dharura kwa msingi mmoja.',
      plain: 'Treasury adds day-to-day spending, development, county transfers and a reserve for unexpected costs on the same basis.',
    },
    measure: { en: 'Expenditure and net lending', sw: 'Matumizi na mikopo halisi', plain: 'Planned expenditure and net lending' },
    destination: { en: 'Explore the Budget page', sw: 'Chunguza ukurasa wa Bajeti', plain: 'See the Budget page' },
  },
  revenue: {
    title: { en: 'Where revenue comes from', sw: 'Mapato yanatoka wapi', plain: 'Where revenue comes from' },
    description: {
      en: 'The Treasury’s total revenue here includes ordinary revenue and money ministries raise or retain under appropriations in aid. Grants appear separately in the framework.',
      sw: 'Jumla ya mapato ya Hazina hapa inajumuisha mapato ya kawaida na fedha ambazo wizara zinakusanya au kubakiza kama mapato ya matumizi. Ruzuku zinaonyeshwa kando katika mfumo huu.',
      plain: 'This total includes ordinary revenue and money ministries collect for their work. Treasury lists grants separately.',
    },
    measure: { en: 'Revenue including appropriations in aid', sw: 'Mapato pamoja na mapato yanayotumika moja kwa moja', plain: 'Revenue including money ministries collect' },
    destination: { en: 'Read about government revenue', sw: 'Soma kuhusu mapato ya serikali', plain: 'Read about government revenue' },
  },
  financing: {
    title: { en: 'How the funding gap is financed', sw: 'Jinsi pengo la fedha linavyofadhiliwa', plain: 'How the budget covers the funding gap' },
    description: {
      en: 'The financing figure combines net domestic and foreign financing for the budget year. It describes this year’s plan. The Debt page explains the outstanding balance.',
      sw: 'Takwimu hii inajumuisha ufadhili halisi wa ndani na nje kwa mwaka wa bajeti. Inaeleza mpango wa mwaka huu. Ukurasa wa Deni unaeleza deni lililosalia.',
      plain: 'This is the planned net financing from inside and outside Kenya for the year. Follow the Debt link to learn about the balance owed.',
    },
    measure: { en: 'Total net financing', sw: 'Jumla ya ufadhili halisi', plain: 'Total net financing' },
    destination: { en: 'Explore national debt', sw: 'Chunguza deni la kitaifa', plain: 'Explore national debt' },
  },
  counties: {
    title: { en: 'What the budget plans for counties', sw: 'Mchango uliopangwa kwa kaunti katika bajeti', plain: 'What the budget plans to transfer to counties' },
    description: {
      en: 'County transfers are an allocation in the national plan. The Controller of Budget reports county spending separately as counties use their budgets.',
      sw: 'Uhamisho wa fedha kwa kaunti ni mgao katika mpango wa kitaifa. Mdhibiti wa Bajeti huripoti matumizi ya kaunti kando kaunti zinapotumia bajeti zao.',
      plain: 'The national budget plans to send this amount to counties. Follow the money shows how county spending is reported.',
    },
    measure: { en: 'Planned county transfers', sw: 'Uhamisho uliopangwa kwa kaunti', plain: 'Planned transfers to counties' },
    destination: { en: 'Follow county spending', sw: 'Fuatilia matumizi ya kaunti', plain: 'Follow county spending' },
  },
} as const;
