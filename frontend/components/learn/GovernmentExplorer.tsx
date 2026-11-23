'use client';

import { useLang } from '@/lib/i18n/LangProvider';
import { GOVERNMENT_MESSAGES } from '@/lib/i18n/messages/government';
import { Building2, ChevronDown, ChevronRight, Landmark, MapPin, Scale, Shield, type LucideIcon } from 'lucide-react';
import Link from 'next/link';
import { useId, useState } from 'react';

interface BranchDetail {
  office: string;
  description: string;
}

interface Branch {
  id: 'executive' | 'legislature' | 'judiciary';
  icon: LucideIcon;
  details: BranchDetail[];
  funFact: string;
}

const branches: Branch[] = [
  {
    id: 'executive',
    icon: Shield,
    details: [
      {
        office: 'President',
        description:
          'Head of State, Government, and Commander-in-Chief of the Kenya Defence Forces.',
      },
      {
        office: 'Deputy President',
        description: 'Principal assistant to the President and succession line.',
      },
      {
        office: 'Cabinet Secretaries',
        description:
          '14–22 secretaries appointed by the President, approved by the National Assembly. Each heads a ministry.',
      },
      { office: 'Attorney General', description: 'Principal legal adviser of the Government.' },
      {
        office: 'Director of Public Prosecutions',
        description: 'Independent office that decides whether to prosecute criminal cases.',
      },
    ],
    funFact:
      "The President must receive over 50% of votes cast nationally AND at least 25% in more than half of Kenya's 47 counties to win.",
  },
  {
    id: 'legislature',
    icon: Landmark,
    details: [
      {
        office: 'National Assembly (350 members, incl. Speaker)',
        description:
          'Enacts legislation, determines taxation & expenditures, and approves or rejects presidential nominees.',
      },
      {
        office: 'Senate (68 members, incl. Speaker)',
        description:
          'Protects county interests, participates in law-making affecting counties, and determines allocation of national revenue among counties.',
      },
      { office: 'Speaker (each House)', description: 'Presides over debates and maintains order.' },
      {
        office: 'Parliamentary Committees',
        description:
          'Committees like Public Accounts (PAC) and Public Investments (PIC) scrutinise government spending.',
      },
    ],
    funFact:
      "Kenya's Parliament sits in a building originally constructed in 1954. The National Assembly and Senate operate as a bicameral legislature since 2013.",
  },
  {
    id: 'judiciary',
    icon: Scale,
    details: [
      {
        office: 'Supreme Court',
        description:
          'Highest court — hears appeals from the Court of Appeal and presidential election petitions. Has 7 judges.',
      },
      {
        office: 'Court of Appeal',
        description: 'Hears appeals from the High Court and any other court prescribed by law.',
      },
      {
        office: 'High Court',
        description:
          'Original jurisdiction on constitutional matters, human rights, and judicial review.',
      },
      {
        office: "Magistrates' Courts",
        description: 'Handle the majority of criminal and civil cases at the local level.',
      },
      {
        office: 'Judicial Service Commission',
        description:
          'Recommends judicial appointments and handles discipline of judges and magistrates.',
      },
    ],
    funFact:
      'The Judiciary successfully nullified the 2017 presidential election — a first in African history — citing irregularities in the process.',
  },
];

const tiers = [
  {
    id: 'national',
    icon: Building2,
    functions: [
      'foreignAffairs', 'security', 'economicPlanning',
      'immigration', 'publicWorks', 'educationStandards',
    ],
  },
  {
    id: 'county',
    icon: MapPin,
    functions: ['health', 'earlyEducation', 'roads', 'agriculture', 'trade', 'countyPlanning'],
  },
] as const;

const focusClass = 'focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-signal-good';
const linkClass = `inline-flex min-h-11 max-w-full items-center gap-1 rounded px-1 text-sm font-semibold text-neutral-text underline decoration-neutral-border underline-offset-4 hover:decoration-current ${focusClass}`;

const parliamentBudget =
  'https://newsite.treasury.go.ke/sites/default/files/Budget%20Books/Budget%20books%202026-2027/FY%202026%202027%20Programme%20Based%20Budget%20Book_Approved.pdf#page=10';

export default function GovernmentExplorer() {
  const { lang } = useLang();
  const id = useId();
  const [expanded, setExpanded] = useState<Branch['id'] | null>(null);
  const copy = (key: keyof typeof GOVERNMENT_MESSAGES) => GOVERNMENT_MESSAGES[key][lang];

  return (
    <div data-government-explorer className='min-w-0 space-y-10'>
      <section aria-labelledby={`${id}-branches`}>
        <h2 id={`${id}-branches`} className='font-display text-2xl font-semibold text-neutral-text'>
          {copy('branches')}
        </h2>
        <p className='mb-4 mt-1 text-sm text-neutral-muted'>{copy('branchInstructions')}</p>
        <ul role='list' className='divide-y divide-neutral-border rounded border border-neutral-border bg-surface-base'>
          {branches.map(({ id: key, icon: Icon, details, funFact }) => {
            const open = expanded === key;
            const panel = `${id}-${key}`;
            return (
              <li key={key}>
                <h3>
                  <button
                    type='button'
                    aria-expanded={open}
                    aria-controls={panel}
                    onClick={() => setExpanded(current => current === key ? null : key)}
                    className={`flex min-h-11 w-full items-start gap-3 rounded px-3 py-3 text-left hover:bg-surface-sunken sm:px-4 ${focusClass}`}>
                    <Icon size={20} aria-hidden='true' className='mt-1 shrink-0 text-neutral-text' />
                    <span className='min-w-0 flex-1'>
                      <span className='block break-words font-display text-xl font-semibold text-neutral-text'>
                        {copy(key)}
                      </span>
                      <span className='block break-words text-sm font-normal text-neutral-text'>
                        {copy(`${key}Description`)}
                      </span>
                    </span>
                    <ChevronDown size={18} aria-hidden='true'
                      className={`mt-1 shrink-0 text-neutral-muted ${open ? 'rotate-180' : ''}`} />
                  </button>
                </h3>
                {key === 'legislature' && (
                  <div className='ml-10 flex flex-wrap items-center gap-x-3 px-1 pb-1 sm:ml-11'>
                    <a href={parliamentBudget} className={linkClass}>
                      <span className='min-w-0 break-words'>{copy('parliamentBudget')}</span>
                      <ChevronRight aria-hidden='true' size={16} className='shrink-0' />
                    </a>
                    <Link href='/learn?article=95' className={linkClass}>
                      {copy('article95')} <ChevronRight aria-hidden='true' size={16} className='shrink-0' />
                    </Link>
                  </div>
                )}
                <div id={panel} hidden={!open} className='border-t border-neutral-border px-3 pb-4 sm:px-4'>
                  <ul lang='en' role='list' className='grid gap-x-5 sm:grid-cols-2'>
                    {details.map(({ office, description }) => (
                      <li key={office} className='min-w-0 border-b border-neutral-border py-3'>
                        <h4 className='break-words text-sm font-semibold text-neutral-text'>{office}</h4>
                        <p className='mt-1 break-words text-sm leading-relaxed text-neutral-muted'>{description}</p>
                      </li>
                    ))}
                  </ul>
                  <p className='mt-3 text-sm leading-relaxed text-neutral-text'>
                    <strong className='font-semibold'>{copy('fact')}</strong>{' '}
                    <span lang='en'>{funFact}</span>
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      <section aria-labelledby={`${id}-devolution`}>
        <h2 id={`${id}-devolution`} className='font-display text-2xl font-semibold text-neutral-text'>
          {copy('devolution')}
        </h2>
        <p className='mb-4 mt-1 text-sm text-neutral-muted'>{copy('devolutionDescription')}</p>
        <div className='grid gap-6 md:grid-cols-2'>
          {tiers.map(({ id: key, icon: Icon, functions }) => (
            <section key={key} aria-labelledby={`${id}-${key}`} className='min-w-0'>
              <h3 id={`${id}-${key}`} className='flex items-center gap-2 font-display text-xl font-semibold text-neutral-text'>
                <Icon aria-hidden='true' size={20} className='shrink-0' /> {copy(key)}
              </h3>
              <ul role='list' className='mt-2 divide-y divide-neutral-border border-y border-neutral-border'>
                {functions.map(item => (
                  <li key={item} className='break-words py-2.5 text-sm font-semibold text-neutral-text'>{copy(item)}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
        <p lang='en' className='mt-4 border-l-2 border-neutral-border pl-3 text-sm leading-relaxed text-neutral-muted'>
          The Commission on Revenue Allocation (CRA) <strong>recommends</strong> how revenue
          should be shared between the two levels; Parliament decides, through the Division of
          Revenue Act and the County Allocation of Revenue Act each year. The Constitution sets
          a floor: counties receive at least <strong>15 %</strong> of revenue raised nationally,
          calculated on the <strong>most recently audited</strong> national accounts approved by
          the National Assembly — usually two to three years old, so the share looks small
          against the current year&apos;s revenue.
        </p>
      </section>
    </div>
  );
}
