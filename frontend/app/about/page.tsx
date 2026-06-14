'use client';

import PageShell from '@/components/layout/PageShell';
import { motion } from 'framer-motion';
import {
  BarChart3,
  BookOpen,
  Database,
  ExternalLink,
  Eye,
  Globe,
  Heart,
  Scale,
  Search,
  Shield,
  Target,
  Users,
} from 'lucide-react';
import Link from 'next/link';

/* ── Appearance helpers ── */
const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] },
  }),
};

/* ── Data ── */
const DATA_SOURCES = [
  {
    name: 'Office of the Auditor General',
    url: 'https://www.oagkenya.go.ke',
    desc: 'Federal and county audit reports',
  },
  {
    name: 'Controller of Budget',
    url: 'https://cob.go.ke',
    desc: 'Budget implementation reports',
  },
  {
    name: 'Kenya National Bureau of Statistics',
    url: 'https://www.knbs.or.ke',
    desc: 'Population, GDP, and economic indicators',
  },
  {
    name: 'The National Treasury',
    url: 'https://www.treasury.go.ke',
    desc: 'National budget documents and debt data',
  },
  {
    name: 'Commission on Revenue Allocation',
    url: 'https://www.crakenya.org',
    desc: 'County revenue sharing formulas',
  },
];

const PRINCIPLES = [
  {
    icon: Eye,
    title: 'Radical Transparency',
    desc: 'Every data point is sourced and traceable. We show you exactly where the numbers come from.',
  },
  {
    icon: Shield,
    title: 'Non-Partisan',
    desc: 'We present facts without political spin. The data speaks for itself.',
  },
  {
    icon: Users,
    title: 'Citizen-First',
    desc: 'Designed for everyday Kenyans — not bureaucrats. Clear language, visual data, zero jargon.',
  },
  {
    icon: Scale,
    title: 'Accountability',
    desc: 'We make it easy to compare promises vs performance across all 47 counties.',
  },
];

const FEATURES = [
  { icon: BarChart3, label: 'National debt tracking, updated nightly' },
  { icon: Search, label: 'County-level budget explorer for all 47 counties' },
  { icon: BookOpen, label: 'Audit report summaries from the Auditor General' },
  { icon: Database, label: 'Economic indicators (GDP, inflation, population)' },
  { icon: Target, label: 'Budget vs actual spending comparison' },
  { icon: Globe, label: 'Open data — free for journalists, researchers & citizens' },
];

export default function AboutPage() {
  return (
    <PageShell title='About AuditGava' subtitle='Empowering Kenyans with financial transparency'>
      {/* ── Mission ── */}
      <section className='space-y-4'>
        <div className='flex items-center gap-3 mb-2'>
          <div className='w-10 h-10 rounded-xl bg-gov-sage/15 flex items-center justify-center border border-gov-sage/20'>
            <Heart className='w-5 h-5 text-gov-sage' />
          </div>
          <h2 className='font-display text-2xl text-neutral-text'>Our Mission</h2>
        </div>
        <div className='bg-gradient-to-r from-gov-sage/5 to-gov-gold/5 rounded-2xl p-6 border border-gov-sage/10'>
          <p className='text-neutral-text leading-relaxed text-[15px]'>
            <strong className='text-gov-forest dark:text-emerald-100'>AuditGava</strong> — <em>"Gava"</em> is Kenyan
            Swahili slang for government, widely used in everyday conversation. We chose it because
            this platform is built for everyday Kenyans, not policy insiders. AuditGava is a civic
            technology platform that makes Kenya's public finances accessible to every citizen. We
            aggregate audit reports, budget data, debt figures, and economic indicators from
            official government sources — and present them in plain language with clear
            visualisations.
          </p>
          <p className='text-neutral-muted leading-relaxed text-[15px] mt-3'>
            Our goal is simple: when citizens can see where public money goes, they can demand
            better services, reward honest leaders, and build a more accountable Kenya.
          </p>
        </div>
      </section>

      {/* ── Principles ── */}
      <section className='space-y-4'>
        <h2 className='font-display text-2xl text-neutral-text'>Our Principles</h2>
        <div className='grid sm:grid-cols-2 gap-4'>
          {PRINCIPLES.map((p, i) => (
            <motion.div
              key={p.title}
              variants={fadeUp}
              initial='hidden'
              whileInView='show'
              viewport={{ once: true, margin: '-30px' }}
              custom={i}
              className='bg-white dark:bg-surface-base rounded-2xl p-5 border border-neutral-border shadow-surface hover:shadow-elevated transition-shadow'>
              <div className='flex items-start gap-3'>
                <div className='w-9 h-9 rounded-lg bg-gov-sage/10 flex items-center justify-center shrink-0 border border-gov-sage/15'>
                  <p.icon className='w-[18px] h-[18px] text-gov-sage' />
                </div>
                <div>
                  <h3 className='font-semibold text-neutral-text text-sm mb-1'>{p.title}</h3>
                  <p className='text-neutral-muted text-[13px] leading-relaxed'>{p.desc}</p>
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── What we track ── */}
      <section className='space-y-4'>
        <h2 className='font-display text-2xl text-neutral-text'>What We Track</h2>
        <div className='grid sm:grid-cols-2 lg:grid-cols-3 gap-3'>
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.label}
              variants={fadeUp}
              initial='hidden'
              whileInView='show'
              viewport={{ once: true, margin: '-30px' }}
              custom={i}
              className='flex items-center gap-3 bg-white dark:bg-surface-base rounded-xl p-4 border border-neutral-border shadow-surface'>
              <f.icon className='w-5 h-5 text-gov-gold shrink-0' />
              <span className='text-sm text-neutral-text'>{f.label}</span>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ── Data sources ── */}
      <section className='space-y-4'>
        <h2 className='font-display text-2xl text-neutral-text'>Official Data Sources</h2>
        <p className='text-neutral-muted text-sm'>
          All data is sourced from official Kenyan government publications. We never fabricate or
          estimate figures.
        </p>
        <div className='space-y-2'>
          {DATA_SOURCES.map((s, i) => (
            <motion.a
              key={s.name}
              href={s.url}
              target='_blank'
              rel='noopener noreferrer'
              variants={fadeUp}
              initial='hidden'
              whileInView='show'
              viewport={{ once: true, margin: '-20px' }}
              custom={i}
              className='flex items-center justify-between gap-3 bg-white dark:bg-surface-base rounded-xl p-4 border border-neutral-border shadow-surface hover:shadow-elevated hover:border-gov-sage/30 transition-all group'>
              <div>
                <h3 className='font-semibold text-sm text-neutral-text group-hover:text-gov-sage transition-colors'>
                  {s.name}
                </h3>
                <p className='text-xs text-neutral-muted'>{s.desc}</p>
              </div>
              <ExternalLink className='w-4 h-4 text-neutral-muted group-hover:text-gov-sage shrink-0 transition-colors' />
            </motion.a>
          ))}
        </div>
      </section>

      {/* ── Open source (hidden until ready for public launch) ──
      <section className='space-y-4'>
        <h2 className='font-display text-2xl text-neutral-text'>Open Source</h2>
        <div className='bg-gov-dark rounded-2xl p-6 text-white'>
          <div className='flex items-start gap-4'>
            <div className='w-11 h-11 rounded-xl bg-white/10 flex items-center justify-center border border-white/15 shrink-0'>
              <Github className='w-5 h-5 text-white' />
            </div>
            <div>
              <h3 className='font-semibold mb-1'>Built in the open</h3>
              <p className='text-white/60 text-sm leading-relaxed mb-3'>
                AuditGava is open-source software. Journalists, developers, and researchers are
                welcome to inspect our code, report issues, or contribute improvements.
              </p>
              <a
                href='https://github.com/Rodgers31/audit_app'
                target='_blank'
                rel='noopener noreferrer'
                className='inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white/10 border border-white/15 text-sm font-medium hover:bg-white/20 transition-colors'>
                <Github className='w-4 h-4' />
                View on GitHub
                <ExternalLink className='w-3 h-3 ml-1 opacity-50' />
              </a>
            </div>
          </div>
        </div>
      </section>
      ── */}

      {/* ── Contact ── */}
      <section className='space-y-3'>
        <h2 className='font-display text-2xl text-neutral-text'>Contact</h2>
        <div className='bg-white dark:bg-surface-base rounded-2xl p-5 border border-neutral-border shadow-surface'>
          <p className='text-neutral-muted text-sm leading-relaxed'>
            Have a tip, question, or partnership inquiry? Reach out:
          </p>
          <ul className='mt-3 space-y-2 text-sm'>
            <li className='text-neutral-text'>
              Email:{' '}
              <a
                href='mailto:auditgava@gmail.com'
                className='text-gov-sage hover:underline font-medium'>
                auditgava@gmail.com
              </a>
            </li>
            {/* <li className='text-neutral-text'>
              GitHub Issues:{' '}
              <a
                href='https://github.com/Rodgers31/audit_app/issues'
                target='_blank'
                rel='noopener noreferrer'
                className='text-gov-sage hover:underline font-medium'>
                Report a bug or suggest a feature
              </a>
            </li> */}
          </ul>
        </div>
      </section>

      {/* ── Legal links ── */}
      <div className='flex flex-wrap gap-4 pt-2 text-xs text-neutral-900'>
        <Link href='/privacy' className='hover:text-gov-sage transition-colors'>
          Privacy Policy
        </Link>
        <Link href='/terms' className='hover:text-gov-sage transition-colors'>
          Terms of Use
        </Link>
      </div>
    </PageShell>
  );
}
