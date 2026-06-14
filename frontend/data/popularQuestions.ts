/**
 * Popular civic questions — the FAQ shown on the Learn hub.
 *
 * Content principles:
 *   - Questions are phrased the way an ordinary Kenyan would type them.
 *   - Answers cite the constitutional article or Act when possible, because
 *     the point of AuditGava is turning opaque rules into clear facts.
 *   - Each answer is short (2-4 sentences) and can link to deeper reading.
 */

export interface PopularQuestion {
  id: string;
  question: string;
  answer: string;
  /** Shown as a short chip above the question. */
  category: 'Budget' | 'Audit' | 'Debt' | 'Devolution' | 'Citizens' | 'Constitution';
  /** Optional deep-link — article number in the Constitution book. */
  articleNumber?: number;
  /** Optional external link within AuditGava. */
  learnMoreHref?: string;
}

export const POPULAR_QUESTIONS: PopularQuestion[] = [
  {
    id: 'q-auditor-general',
    question: 'Who is the Auditor-General and why do they matter?',
    answer:
      'The Auditor-General is an independent constitutional officer (Article 229) who audits every public entity — national government, counties, courts, and commissions — and publishes the results within six months of year-end. Their report is the single most important accountability document in Kenya: it tells the public whether money was spent lawfully and to effect.',
    category: 'Audit',
    articleNumber: 229,
  },
  {
    id: 'q-equitable-share',
    question: 'How much money do counties get from the national government?',
    answer:
      'The Constitution (Article 203) requires that not less than 15% of the most recent audited national revenue be shared with the 47 counties each year. The exact split between counties is set annually in the Division of Revenue Act and County Allocation of Revenue Act after advice from the Commission on Revenue Allocation.',
    category: 'Budget',
    articleNumber: 203,
  },
  {
    id: 'q-public-debt',
    question: 'Can Kenya borrow money without Parliament knowing?',
    answer:
      'No. Article 214 defines public debt as all financial obligations attendant to Kenyan loans, and the Public Finance Management Act requires every government loan to be laid before Parliament. Any guarantee or borrowing outside this process is unconstitutional.',
    category: 'Debt',
    articleNumber: 214,
  },
  {
    id: 'q-procurement',
    question: 'Why do I keep hearing about "procurement" in audit reports?',
    answer:
      'Procurement is how government buys goods and services. Article 227 demands it be "fair, equitable, transparent, competitive and cost-effective." Most audit queries trace back to procurement that skipped these principles — single-sourced deals, inflated prices, or missing records.',
    category: 'Audit',
    articleNumber: 227,
  },
  {
    id: 'q-chapter-6',
    question: 'What does "Chapter 6" actually say about leaders?',
    answer:
      "Chapter 6 (Articles 73-80) treats public office as a public trust, not a personal prize. Leaders must avoid conflicts of interest, refuse gifts that could compromise them, keep no secret foreign accounts, and be accountable to the public. Breaching these rules can lead to dismissal and permanent disqualification.",
    category: 'Constitution',
    articleNumber: 73,
  },
  {
    id: 'q-county-vs-national',
    question: 'What do counties do that the national government does not?',
    answer:
      'The Fourth Schedule splits functions. Counties handle local matters — county health services, pre-primary education, local roads, agriculture, water, trade licences. National government handles foreign affairs, defence, immigration, universities, the judiciary, and national-level policy. Both levels are distinct but required to cooperate (Article 189).',
    category: 'Devolution',
    articleNumber: 186,
  },
  {
    id: 'q-public-participation',
    question: 'Do I have a right to be consulted on my county budget?',
    answer:
      'Yes. Article 10 lists "participation of the people" as a binding national value, and Article 201(a) requires openness and public participation in financial matters. County governments must hold public hearings before approving budgets — and the Auditor-General looks for evidence of this.',
    category: 'Citizens',
    articleNumber: 201,
  },
  {
    id: 'q-equalisation-fund',
    question: 'What is the Equalisation Fund?',
    answer:
      'Article 204 set up a fund equal to 0.5% of audited national revenue to be spent on basic services — water, roads, health, electricity — in areas historically marginalised. It runs for at least 20 years from 2010 and can only be used for those purposes.',
    category: 'Budget',
    articleNumber: 204,
  },
  {
    id: 'q-report-corruption',
    question: 'Where do I report misuse of public money?',
    answer:
      'The Ethics and Anti-Corruption Commission (EACC), established under Article 79, is the constitutional watchdog for leadership integrity. You can also raise issues with the Office of the Auditor-General during the audit cycle, or your county public participation forum.',
    category: 'Citizens',
    articleNumber: 79,
  },
  {
    id: 'q-why-grade',
    question: 'What does AuditGava\'s "Audit Grade" mean?',
    answer:
      'The Audit Grade is a 0–100 score that translates Auditor-General findings into a letter. It penalises unresolved findings, critical queries, and the share of the budget flagged as improper. A = clean, B = minor issues, C = material issues, D = widespread issues, F = systemic failure. Click any badge on a county page to see how the score was calculated.',
    category: 'Audit',
    learnMoreHref: '/counties',
  },
];
