'use client';

import { motion, useReducedMotion } from 'framer-motion';
import { BadgeDollarSign, FileSearch2, Landmark, WalletCards } from 'lucide-react';

const STAGES = [
  {
    label: 'Allocation',
    detail: 'Parliament approves and government allocates',
    Icon: Landmark,
  },
  {
    label: 'Borrowing',
    detail: 'Loans, bonds and other public liabilities',
    Icon: BadgeDollarSign,
  },
  {
    label: 'Spending',
    detail: 'Funds move through ministries and counties',
    Icon: WalletCards,
  },
  {
    label: 'Audit outcome',
    detail: 'The public record shows what was questioned',
    Icon: FileSearch2,
  },
];

export default function MoneyTraceRibbon() {
  const reduceMotion = useReducedMotion();

  return (
    <section aria-labelledby='money-trace-title' className='ledger-panel overflow-hidden'>
      <div className='flex flex-col gap-3 border-b border-neutral-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6'>
        <div>
          <p className='source-label'>How to read the evidence</p>
          <h2 id='money-trace-title' className='mt-1 text-sm font-semibold text-gov-dark dark:text-white'>
            Follow one public shilling from approval to audit
          </h2>
        </div>
        <p className='font-mono text-[11px] uppercase tracking-[0.11em] text-gov-copper'>
          Trace the money · verify the source
        </p>
      </div>

      <div className='relative px-4 py-5 sm:px-6 sm:py-6'>
        <motion.span
          aria-hidden='true'
          className='trace-draw-x absolute bottom-6 left-[12.5%] right-[12.5%] hidden h-0.5 origin-left bg-gov-copper sm:block'
          initial={false}
          whileInView={{ scaleX: 1 }}
          viewport={{ once: true, amount: 0.7 }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
        />
        <motion.span
          aria-hidden='true'
          className='trace-draw-y absolute bottom-[12%] left-[31px] top-[12%] w-0.5 origin-top bg-gov-copper sm:hidden'
          initial={false}
          whileInView={{ scaleY: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.65, ease: 'easeOut' }}
        />

        <ol className='relative grid gap-5 sm:grid-cols-4 sm:gap-0'>
          {STAGES.map(({ label, detail, Icon }, index) => (
            <motion.li
              key={label}
              initial={false}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.7 }}
              transition={{ duration: 0.24, delay: reduceMotion ? 0 : 0.12 + index * 0.08 }}
              className='trace-step relative grid min-h-20 grid-cols-[40px_1fr] gap-3 sm:block sm:min-h-32 sm:border-r sm:border-neutral-border sm:px-5 sm:last:border-r-0'>
              <span className='relative z-[1] grid h-8 w-8 rotate-45 place-items-center border-2 border-gov-copper bg-surface-base sm:absolute sm:bottom-[-1px] sm:left-1/2 sm:-translate-x-1/2'>
                <Icon className='h-4 w-4 -rotate-45 text-gov-dark dark:text-white' aria-hidden='true' />
              </span>
              <div className='sm:pb-10'>
                <p className='font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-gov-copper'>
                  {String(index + 1).padStart(2, '0')} · {label}
                </p>
                <p className='mt-2 max-w-[25ch] text-xs leading-5 text-neutral-muted'>{detail}</p>
              </div>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}
