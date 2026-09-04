/**
 * GovernmentExplorer – Interactive visualisation of Kenya's government structure.
 *
 * Three clickable branches (Executive, Legislature, Judiciary) expand to show
 * key offices, functions, and fun facts.  A second tier shows the National ↔
 * County relationship under devolution.
 */
'use client';

import { AnimatePresence, motion } from 'framer-motion';
import {
  Building2,
  ChevronDown,
  Gavel,
  Landmark,
  MapPin,
  Scale,
  Shield,
  Users,
} from 'lucide-react';
import { useState } from 'react';

interface BranchDetail {
  office: string;
  description: string;
}

interface Branch {
  id: string;
  title: string;
  tagline: string;
  icon: React.ElementType;
  gradient: string;
  iconBg: string;
  details: BranchDetail[];
  funFact: string;
}

const branches: Branch[] = [
  {
    id: 'executive',
    title: 'Executive',
    tagline: 'Implements laws & runs the country',
    icon: Shield,
    gradient: 'from-gov-forest to-emerald-700',
    iconBg: 'bg-emerald-100 text-emerald-700',
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
    title: 'Legislature',
    tagline: 'Makes laws & controls public spending',
    icon: Landmark,
    gradient: 'from-sky-600 to-indigo-700',
    iconBg: 'bg-sky-100 text-sky-700',
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
    title: 'Judiciary',
    tagline: 'Interprets the Constitution & settles disputes',
    icon: Scale,
    gradient: 'from-amber-600 to-orange-700',
    iconBg: 'bg-amber-100 text-amber-700',
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

interface DevolutionTier {
  id: string;
  title: string;
  icon: React.ElementType;
  items: string[];
  color: string;
}

const devolutionTiers: DevolutionTier[] = [
  {
    id: 'national',
    title: 'National Government',
    icon: Building2,
    items: [
      'Foreign affairs & international trade',
      'National defence & security',
      'Monetary policy & national economic planning',
      'Immigration & citizenship',
      'National public works & housing policy',
      'Education curriculum & standards',
    ],
    color: 'border-gov-forest bg-gov-forest/5',
  },
  {
    id: 'county',
    title: 'County Governments (47)',
    icon: MapPin,
    items: [
      'County health services & ambulances',
      'Pre-primary education & childcare',
      'County roads & public transport',
      'Agriculture, livestock & fisheries',
      'Trade development & regulation',
      'County planning & development',
    ],
    color: 'border-gov-gold bg-gov-gold/5',
  },
];

export default function GovernmentExplorer() {
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggle = (id: string) => setExpanded((prev) => (prev === id ? null : id));

  return (
    <div className='space-y-10'>
      {/* ── Three Branches ── */}
      <div>
        <h3 className='font-display text-2xl text-gov-dark dark:text-white mb-1'>Three Arms of Government</h3>
        <p className='text-sm text-neutral-muted mb-6'>
          Click a branch to explore its structure and functions
        </p>

        <div className='space-y-4'>
          {branches.map((b) => {
            const Icon = b.icon;
            const isOpen = expanded === b.id;

            return (
              <div
                key={b.id}
                className='rounded-2xl overflow-hidden border border-white/50 shadow-surface'>
                {/* Header */}
                <motion.button
                  onClick={() => toggle(b.id)}
                  className='w-full flex items-center gap-4 p-5 bg-white/60 dark:bg-surface-elevated backdrop-blur hover:bg-white/80 dark:bg-surface-elevated transition-colors text-left'
                  whileTap={{ scale: 0.995 }}>
                  <div
                    className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${b.iconBg}`}>
                    <Icon size={24} />
                  </div>
                  <div className='flex-1 min-w-0'>
                    <h4 className='font-bold text-gov-dark dark:text-white text-lg'>{b.title}</h4>
                    <p className='text-sm text-neutral-muted truncate'>{b.tagline}</p>
                  </div>
                  <motion.div
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ duration: 0.25 }}>
                    <ChevronDown size={20} className='text-neutral-muted' />
                  </motion.div>
                </motion.button>

                {/* Expandable body */}
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                      className='overflow-hidden'>
                      <div className='px-5 pb-5 pt-2 space-y-4'>
                        {/* Details list */}
                        <div className='grid gap-3 sm:grid-cols-2'>
                          {b.details.map((d) => (
                            <div
                              key={d.office}
                              className='rounded-xl bg-white/50 dark:bg-surface-elevated border border-white/40 p-4'>
                              <h5 className='font-semibold text-gov-dark dark:text-white text-sm mb-1'>
                                {d.office}
                              </h5>
                              <p className='text-xs leading-relaxed text-neutral-muted'>
                                {d.description}
                              </p>
                            </div>
                          ))}
                        </div>

                        {/* Fun fact */}
                        <div className={`rounded-xl bg-gradient-to-r ${b.gradient} p-4 text-white`}>
                          <div className='flex items-start gap-2'>
                            <Gavel size={16} className='mt-0.5 shrink-0 text-white/70' />
                            <div>
                              <span className='text-xs font-semibold uppercase tracking-wide text-white/70'>
                                Did you know?
                              </span>
                              <p className='text-sm leading-relaxed mt-1'>{b.funFact}</p>
                            </div>
                          </div>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Devolution Section ── */}
      <div>
        <h3 className='font-display text-2xl text-gov-dark dark:text-white mb-1'>Devolution: Power Shared</h3>
        <p className='text-sm text-neutral-muted mb-6'>
          The 2010 Constitution created two levels of government — national and county
        </p>

        <div className='grid gap-4 md:grid-cols-2'>
          {devolutionTiers.map((tier) => {
            const Icon = tier.icon;
            return (
              <motion.div
                key={tier.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5 }}
                className={`rounded-2xl border-2 ${tier.color} p-5`}>
                <div className='flex items-center gap-3 mb-4'>
                  <Icon size={22} className='text-gov-dark dark:text-white' />
                  <h4 className='font-bold text-gov-dark dark:text-white'>{tier.title}</h4>
                </div>
                <ul className='space-y-2'>
                  {tier.items.map((item) => (
                    <li key={item} className='flex items-start gap-2 text-sm text-gov-dark/80 dark:text-white/80'>
                      <span className='mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-gov-sage' />
                      {item}
                    </li>
                  ))}
                </ul>
              </motion.div>
            );
          })}
        </div>

        {/* Connector line / CRA note */}
        <div className='flex items-center justify-center gap-3 mt-5'>
          <Users size={16} className='text-gov-sage' />
          <span className='text-xs text-neutral-muted text-center'>
            {/* Two errors corrected here (credibility audit F20).
                (a) Article 216 makes the CRA a RECOMMENDING body — Parliament
                decides, through the Division of Revenue Act and the County
                Allocation of Revenue Act. Saying CRA "ensures" misstates a
                constitutional body's powers.
                (b) Article 203(2)-(3): the floor is 15% of revenue raised
                nationally, calculated on the MOST RECENTLY AUDITED accounts
                approved by the National Assembly — typically two to three years
                behind. Omitting that is why the equitable share (~KES 400B)
                looks like a breach against current revenue (~KES 2.9T): it is
                measured against a much older, smaller base. */}
            The Commission on Revenue Allocation (CRA) <strong>recommends</strong> how revenue
            should be shared between the two levels; Parliament decides, through the Division of
            Revenue Act and the County Allocation of Revenue Act each year. The Constitution sets
            a floor: counties receive at least <strong>15 %</strong> of revenue raised nationally,
            calculated on the <strong>most recently audited</strong> national accounts approved by
            the National Assembly — usually two to three years old, so the share looks small
            against the current year&apos;s revenue.
          </span>
        </div>
      </div>
    </div>
  );
}
