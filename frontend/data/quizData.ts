/**
 * Comprehensive quiz data for the Kenya Government Learning Hub.
 *
 * Categories cover the Constitution, government structure, public finance,
 * devolution, rights & freedoms, and the audit/accountability system.
 * Each question includes an explanation shown after the user answers.
 */

export interface QuizQuestion {
  id: string;
  question: string;
  options: string[];
  correctIndex: number;
  explanation: string;
  difficulty: 'easy' | 'medium' | 'hard';
  language?: 'en' | 'sw';
  context?: string;
  sourceUrl?: string;
}

export interface QuizCategory {
  id: string;
  title: string;
  description: string;
  emoji: string;
  gradient: string;
  questions: QuizQuestion[];
}

export const quizCategories: QuizCategory[] = [
  /* ═══════════════════════════════════════════
   * 1. THE CONSTITUTION
   * ═══════════════════════════════════════════ */
  {
    id: 'constitution',
    title: 'The Constitution',
    description: "Test your knowledge of Kenya's 2010 Constitution",
    emoji: '📜',
    gradient: 'from-amber-500 to-orange-600',
    questions: [
      {
        id: 'const-1',
        question: "When was Kenya's current Constitution promulgated?",
        options: ['2005', '2008', '2010', '2013'],
        correctIndex: 2,
        explanation:
          'The Constitution of Kenya 2010 was promulgated on 27 August 2010, replacing the 1963 independence constitution after a national referendum.',
        difficulty: 'easy',
      },
      {
        id: 'const-2',
        question: 'How many chapters does the Constitution of Kenya have?',
        options: ['14', '16', '18', '20'],
        correctIndex: 2,
        explanation:
          'The Constitution has 18 chapters, starting with "Sovereignty of the People" and ending with "Transitional and Consequential Provisions."',
        difficulty: 'medium',
      },
      {
        id: 'const-3',
        question:
          'What percentage of votes was required to pass the 2010 Constitution in the referendum?',
        options: [
          '50% + 1',
          'Two-thirds majority',
          '75% majority',
          'Simple majority in 5 of 8 provinces',
        ],
        correctIndex: 0,
        explanation:
          'A simple majority (50% + 1) was required. The Constitution was approved by 67% of voters.',
        difficulty: 'medium',
      },
      {
        id: 'const-4',
        question: 'Which chapter of the Constitution contains the Bill of Rights?',
        options: ['Chapter 2', 'Chapter 4', 'Chapter 6', 'Chapter 10'],
        correctIndex: 1,
        explanation:
          'Chapter 4 is the Bill of Rights (Articles 19-59), one of the most progressive in Africa, covering civil, political, economic, social, and cultural rights.',
        difficulty: 'hard',
      },
      {
        id: 'const-5',
        question: 'What is the supreme law of the Republic of Kenya?',
        options: ['Acts of Parliament', 'Presidential decrees', 'The Constitution', 'County laws'],
        correctIndex: 2,
        explanation:
          'Article 2(1) states: "This Constitution is the supreme law of the Republic and binds all persons and all State organs at both levels of government."',
        difficulty: 'easy',
      },
      {
        id: 'const-6',
        question: 'According to the Constitution, sovereignty belongs to whom?',
        options: ['The President', 'Parliament', 'The People of Kenya', 'The Judiciary'],
        correctIndex: 2,
        explanation:
          'Article 1(1): "All sovereign power belongs to the people of Kenya and shall be exercised only in accordance with this Constitution."',
        difficulty: 'easy',
      },
    ],
  },

  /* ═══════════════════════════════════════════
   * 2. GOVERNMENT STRUCTURE
   * ═══════════════════════════════════════════ */
  {
    id: 'government',
    title: 'Government Structure',
    description: "How Kenya's three arms of government work",
    emoji: '🏛️',
    gradient: 'from-emerald-500 to-teal-600',
    questions: [
      {
        id: 'gov-1',
        question: 'What are the three arms/branches of the Kenya Government?',
        options: [
          'Executive, Legislative, Judiciary',
          'President, Senate, Courts',
          'National, County, Municipal',
          'Cabinet, Parliament, Police',
        ],
        correctIndex: 0,
        explanation:
          'Chapter 9 (Executive), Chapter 8 (Legislature), and Chapter 10 (Judiciary) establish the three separate arms with checks and balances.',
        difficulty: 'easy',
      },
      {
        id: 'gov-2',
        question: 'How many members does the National Assembly have?',
        options: ['290', '349', '350', '416'],
        correctIndex: 2,
        explanation:
          'Article 97: The National Assembly has 350 members — 290 elected from constituencies, 47 women county reps, 12 nominated members, and the Speaker (ex officio).',
        difficulty: 'medium',
      },
      {
        id: 'gov-3',
        question: 'How many members does the Senate have?',
        options: ['47', '67', '68', '97'],
        correctIndex: 2,
        explanation:
          'Article 98: The Senate has 68 members — 47 elected senators (one per county), 16 women nominees, 2 youth nominees, 2 disability nominees, and the Speaker (ex officio).',
        difficulty: 'medium',
      },
      {
        id: 'gov-4',
        question: 'Who is the head of the Judiciary in Kenya?',
        options: [
          'Attorney General',
          'Chief Justice',
          'Director of Public Prosecutions',
          'Law Society President',
        ],
        correctIndex: 1,
        explanation:
          'The Chief Justice heads the Judiciary and presides over the Supreme Court. The position is established under Article 161 of the Constitution.',
        difficulty: 'easy',
      },
      {
        id: 'gov-5',
        question: 'What is the maximum number of cabinet secretaries the President can appoint?',
        options: ['14', '18', '22', '25'],
        correctIndex: 2,
        explanation:
          'Article 152(1)(d) states the Cabinet consists of not fewer than 14 and not more than 22 Cabinet Secretaries.',
        difficulty: 'hard',
      },
      {
        id: 'gov-6',
        question:
          'Which body has the power to remove the President from office through impeachment?',
        options: ['Supreme Court', 'Senate', 'National Assembly', 'Both Houses of Parliament'],
        correctIndex: 3,
        explanation:
          'Article 145: Impeachment is initiated by the National Assembly (by at least a third), then tried by the Senate which needs a two-thirds vote to remove.',
        difficulty: 'hard',
      },
    ],
  },

  /* ═══════════════════════════════════════════
   * 3. DEVOLUTION & COUNTIES
   * ═══════════════════════════════════════════ */
  {
    id: 'devolution',
    title: 'Devolution & Counties',
    description: "Kenya's county governments and how they serve you",
    emoji: '🗺️',
    gradient: 'from-violet-500 to-purple-600',
    questions: [
      {
        id: 'dev-1',
        question: 'How many counties does Kenya have?',
        options: ['44', '47', '50', '54'],
        correctIndex: 1,
        explanation:
          'Kenya has 47 counties. Article 6(1) refers to the First Schedule, which lists all 47 by name.',
        difficulty: 'easy',
      },
      {
        id: 'dev-2',
        question:
          'What is the minimum share of national revenue that must go to county governments?',
        options: ['10%', '15%', '20%', '25%'],
        correctIndex: 1,
        explanation:
          'Article 203(2) states that county governments collectively receive not less than 15% of all revenue collected by the national government.',
        difficulty: 'medium',
      },
      {
        id: 'dev-3',
        question:
          'Which body recommends the revenue-sharing formula between national and county governments?',
        options: [
          'Treasury',
          'Commission on Revenue Allocation (CRA)',
          'Controller of Budget',
          'Auditor General',
        ],
        correctIndex: 1,
        explanation:
          'The CRA (Article 216) recommends the basis for equitable sharing of revenue between national and county governments.',
        difficulty: 'medium',
      },
      {
        id: 'dev-4',
        question: 'Which of these is NOT a function of county governments?',
        options: ['Health services', 'National defense', 'County roads', 'Agriculture'],
        correctIndex: 1,
        explanation:
          'National defense is a national government function (Fourth Schedule, Part 1). Counties handle health facilities, local roads, agriculture, and many other local services.',
        difficulty: 'easy',
      },
      {
        id: 'dev-5',
        question: 'What fund was established to provide extra resources to marginalized counties?',
        options: [
          'County Emergency Fund',
          'Equalisation Fund',
          'Constituency Development Fund',
          'County Stabilisation Fund',
        ],
        correctIndex: 1,
        explanation:
          'Article 204 establishes the Equalisation Fund (0.5% of revenue) for basic services in marginalized areas identified by the CRA.',
        difficulty: 'hard',
      },
      {
        id: 'dev-6',
        question: 'Who leads the county executive committee?',
        options: ['County Commissioner', 'Governor', 'Senator', 'Speaker of the county assembly'],
        correctIndex: 1,
        explanation:
          'Article 179: The county executive committee consists of the county governor, deputy governor, and members appointed by the governor.',
        difficulty: 'easy',
      },
    ],
  },

  /* ═══════════════════════════════════════════
   * 4. PUBLIC FINANCE
   * ═══════════════════════════════════════════ */
  {
    id: 'finance',
    title: 'Public Finance',
    description: 'How Kenya raises and spends public money',
    emoji: '💰',
    gradient: 'from-sky-500 to-blue-600',
    questions: [
      {
        id: 'fin-1',
        question: 'Which institution is responsible for collecting taxes in Kenya?',
        options: [
          'Central Bank',
          'National Treasury',
          'Kenya Revenue Authority (KRA)',
          'Controller of Budget',
        ],
        correctIndex: 2,
        explanation:
          'KRA was established in 1995 to collect revenue on behalf of the government. It administers Income Tax, VAT, Customs Duty, and Excise Duty.',
        difficulty: 'easy',
      },
      {
        id: 'fin-2',
        question:
          'Who is the guardian of public finances, ensuring no money is withdrawn without authorization?',
        options: [
          'Auditor General',
          'Controller of Budget',
          'National Treasury CS',
          'Chief Justice',
        ],
        correctIndex: 1,
        explanation:
          'Article 228: The Controller of Budget oversees implementation of budgets and authorizes withdrawals from public funds.',
        difficulty: 'medium',
      },
      {
        id: 'fin-3',
        question: 'What type of tax is VAT?',
        options: [
          'Direct tax on income',
          'Indirect tax on consumption',
          'Property tax',
          'Capital gains tax',
        ],
        correctIndex: 1,
        explanation:
          "VAT (Value Added Tax) is an indirect consumption tax charged at 16% on most goods and services in Kenya. It's paid by the final consumer.",
        difficulty: 'easy',
      },
      {
        id: 'fin-4',
        question: "Approximately what percentage of Kenya's GDP is the national debt?",
        options: ['About 30%', 'About 50%', 'About 70%', 'About 90%'],
        correctIndex: 2,
        explanation:
          "Kenya's debt-to-GDP ratio has been around 65-70%, exceeding the East African Community convergence criterion of 50%.",
        difficulty: 'medium',
      },
      {
        id: 'fin-5',
        question: 'Which office audits national and county government accounts?',
        options: [
          'Kenya Anti-Corruption Commission',
          'Office of the Auditor General',
          'Controller of Budget',
          'Ethics and Anti-Corruption Commission',
        ],
        correctIndex: 1,
        explanation:
          'Article 229(4) gives the Auditor-General six months from the end of each financial year to audit and report. Under Article 229(7), the report goes to Parliament or the relevant county assembly.',
        difficulty: 'medium',
      },
      {
        id: 'fin-6',
        question: 'What is the Consolidated Fund?',
        options: [
          'A private investment fund',
          'The main government revenue account into which all taxes are paid',
          'A county emergency fund',
          'The pension fund for civil servants',
        ],
        correctIndex: 1,
        explanation:
          'Article 206: The Consolidated Fund receives all money raised or received by the national government (except where an Act of Parliament provides otherwise).',
        difficulty: 'hard',
      },
    ],
  },

  /* ═══════════════════════════════════════════
   * 5. RIGHTS & FREEDOMS
   * ═══════════════════════════════════════════ */
  {
    id: 'rights',
    title: 'Rights & Freedoms',
    description: 'Your rights under the Kenyan Constitution',
    emoji: '⚖️',
    gradient: 'from-rose-500 to-red-600',
    questions: [
      {
        id: 'rights-1',
        question:
          'Under the Bill of Rights, who has the right to access information held by the State?',
        options: ['Every person', 'Only government officials', 'Only journalists', 'Every citizen'],
        correctIndex: 3,
        explanation:
          'Article 35(1): Every citizen has the right of access to information held by the State. Note: this right applies specifically to citizens, not all persons.',
        difficulty: 'easy',
      },
      {
        id: 'rights-2',
        question: 'At what age can a Kenyan citizen register as a voter?',
        options: ['16', '18', '21', '25'],
        correctIndex: 1,
        explanation:
          'Article 83(1): A citizen who has attained the age of 18 years is entitled to be registered as a voter.',
        difficulty: 'easy',
      },
      {
        id: 'rights-3',
        question:
          'The Constitution requires that no more than two-thirds of elected members of any body shall be of the same gender. This is known as?',
        options: [
          'Gender Equality Principle',
          'Affirmative Action Clause',
          'Two-Thirds Gender Rule',
          'Gender Balance Directive',
        ],
        correctIndex: 2,
        explanation:
          'Article 27(8) establishes the two-thirds gender rule, requiring both genders to be represented at all levels of elective and appointive bodies.',
        difficulty: 'medium',
      },
      {
        id: 'rights-4',
        question: 'Which Article protects freedom of expression?',
        options: ['Article 19', 'Article 25', 'Article 33', 'Article 40'],
        correctIndex: 2,
        explanation:
          'Article 33: Every person has the right to freedom of expression, including freedom to seek, receive, or impart information or ideas.',
        difficulty: 'hard',
      },
      {
        id: 'rights-5',
        question: 'Which rights CANNOT be limited even during a state of emergency?',
        options: [
          'Freedom of movement and assembly',
          'Freedom from torture, freedom from slavery, right to a fair trial',
          'Right to own property',
          'Freedom of the press',
        ],
        correctIndex: 1,
        explanation:
          'Article 25: Rights that cannot be limited include freedom from torture, freedom from slavery or servitude, the right to a fair trial, and the right to habeas corpus.',
        difficulty: 'hard',
      },
      {
        id: 'rights-6',
        question:
          'Every person has the right to the highest attainable standard of health. This is under which type of rights?',
        options: [
          'Civil rights',
          'Political rights',
          'Economic and social rights',
          'Environmental rights',
        ],
        correctIndex: 2,
        explanation:
          'Article 43 (Economic and Social Rights) guarantees the right to health, housing, food, clean water, social security, and education.',
        difficulty: 'medium',
      },
    ],
  },

  /* ═══════════════════════════════════════════
   * 6. ACCOUNTABILITY & OVERSIGHT
   * ═══════════════════════════════════════════ */
  {
    id: 'accountability',
    title: 'Accountability & Oversight',
    description: 'How Kenyans hold their leaders accountable',
    emoji: '🔍',
    gradient: 'from-cyan-500 to-indigo-600',
    questions: [
      {
        id: 'acc-1',
        question: 'Chapter 6 of the Constitution covers which topic?',
        options: [
          'The Judiciary',
          'Leadership and Integrity',
          'National Security',
          'Public Finance',
        ],
        correctIndex: 1,
        explanation:
          'Chapter 6 sets ethical standards for state officers: no conflict of interest, full financial disclosure, no bank accounts outside Kenya, and servant leadership.',
        difficulty: 'medium',
      },
      {
        id: 'acc-2',
        question: 'Which commission investigates and fights corruption in Kenya?',
        options: [
          'Kenya National Commission on Human Rights',
          'Ethics and Anti-Corruption Commission (EACC)',
          'Commission on Administrative Justice (Ombudsman)',
          'National Police Service Commission',
        ],
        correctIndex: 1,
        explanation:
          'EACC (Article 79) is mandated to combat and prevent corruption and ensure compliance with Chapter 6 on Leadership and Integrity.',
        difficulty: 'easy',
      },
      {
        id: 'acc-3',
        question:
          'Citizens can recall their Member of Parliament if they are dissatisfied. What percentage of registered voters must petition for recall?',
        options: ['10%', '20%', '30%', '50%'],
        correctIndex: 2,
        explanation:
          'Article 104: A member of Parliament may be removed by petition of 30% of registered voters in the constituency.',
        difficulty: 'hard',
      },
      {
        id: 'acc-4',
        question: 'What is the role of the Commission on Administrative Justice (Ombudsman)?',
        options: [
          'Prosecuting criminals',
          'Investigating maladministration and resolving public complaints',
          'Appointing judges',
          'Collecting taxes',
        ],
        correctIndex: 1,
        explanation:
          'Article 59(4): The Ombudsman investigates complaints about government services, abuse of power, and maladministration at both levels of government.',
        difficulty: 'medium',
      },
      {
        id: 'acc-5',
        question: 'Which type of audit opinion means the government books are clean and accurate?',
        options: [
          'Qualified opinion',
          'Unqualified (clean) opinion',
          'Adverse opinion',
          'Disclaimer of opinion',
        ],
        correctIndex: 1,
        explanation:
          'An unqualified opinion means the financial statements present a true and fair view. Unfortunately, many Kenyan public entities receive qualified or adverse opinions.',
        difficulty: 'medium',
      },
      {
        id: 'acc-6',
        question: 'Public participation is a constitutional requirement for which processes?',
        options: [
          'Only budget-making',
          'Only law-making',
          'Budget-making, law-making, and development planning',
          'Only county planning',
        ],
        correctIndex: 2,
        explanation:
          'Articles 10, 118, 196, and 201 require public participation in legislative processes, budget-making, and county planning as a core national value.',
        difficulty: 'medium',
      },
    ],
  },
];

/* ── Helpers ── */
export function getCategoryById(id: string): QuizCategory | undefined {
  return quizCategories.find((c) => c.id === id);
}

export function getAllQuestions(): QuizQuestion[] {
  return quizCategories.flatMap((c) => c.questions);
}

export function getRandomQuestions(count: number, difficulty?: QuizQuestion['difficulty']): QuizQuestion[] {
  const all = getAllQuestions().filter(question => !difficulty || question.difficulty === difficulty);
  const shuffled = all.sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

export const TOTAL_QUESTIONS = quizCategories.reduce((sum, c) => sum + c.questions.length, 0);
