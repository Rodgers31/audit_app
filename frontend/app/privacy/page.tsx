'use client';

import PageShell from '@/components/layout/PageShell';
import { Shield } from 'lucide-react';
import Link from 'next/link';

const LAST_UPDATED = 'March 1, 2026';

/* Reusable section component */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className='space-y-3'>
      <h2 className='font-display text-xl text-neutral-text'>{title}</h2>
      <div className='text-neutral-muted text-[14px] leading-[1.75] space-y-3'>{children}</div>
    </section>
  );
}

export default function PrivacyPolicyPage() {
  return (
    <PageShell title='Privacy Policy' subtitle='How we handle your data — plainly and honestly'>
      {/* Last updated badge */}
      <div className='flex items-center gap-3 -mt-1'>
        <div className='w-9 h-9 rounded-lg bg-gov-sage/15 flex items-center justify-center border border-gov-sage/20'>
          <Shield className='w-[18px] h-[18px] text-gov-sage' />
        </div>
        <span className='text-xs text-neutral-muted'>
          Last updated: <strong className='text-neutral-text'>{LAST_UPDATED}</strong>
        </span>
      </div>

      {/* ── Overview ── */}
      <Section title='Overview'>
        <p>
          AuditGava (&quot;we&quot;, &quot;us&quot;, &quot;the platform&quot;) is a civic technology
          project that makes Kenya&apos;s public financial data accessible. We are committed to
          treating your personal information with the same transparency we demand from government.
        </p>
        <p>
          This policy explains what data we collect, why, and how we protect it. If anything is
          unclear, email us at{' '}
          <a href='mailto:auditgava@gmail.com' className='text-gov-sage hover:underline'>
            auditgava@gmail.com
          </a>
          .
        </p>
      </Section>

      {/* ── What we collect ── */}
      <Section title='1. Information We Collect'>
        <div className='bg-white dark:bg-surface-base rounded-xl p-5 border border-neutral-border shadow-surface space-y-4'>
          <div>
            <h3 className='font-semibold text-sm text-neutral-text mb-1'>
              Newsletter Subscription
            </h3>
            <p>
              When you subscribe to our newsletter, we collect your <strong>email address</strong>{' '}
              only. We do not require your name, phone number, or any other personal information.
            </p>
          </div>
          <div>
            <h3 className='font-semibold text-sm text-neutral-text mb-1'>
              Account Registration (Optional)
            </h3>
            <p>
              If you create an account to use watchlist and alert features, we store your{' '}
              <strong>email address</strong> and a securely hashed password. We never store
              passwords in plain text.
            </p>
          </div>
          <div>
            <h3 className='font-semibold text-sm text-neutral-text mb-1'>Usage Analytics</h3>
            <p>
              We use <strong>Vercel Analytics</strong> and <strong>Vercel Speed Insights</strong> to
              understand how visitors use the platform (page views, load times). These tools collect{' '}
              <strong>anonymised, aggregate data</strong> — no cookies, no personal identifiers, no
              cross-site tracking.
            </p>
          </div>
          <div>
            <h3 className='font-semibold text-sm text-neutral-text mb-1'>What We Do Not Collect</h3>
            <ul className='list-disc list-inside space-y-1 text-[13px]'>
              <li>We do not use advertising cookies or trackers</li>
              <li>We do not collect financial or payment information</li>
              <li>We do not collect location data beyond country-level (from IP)</li>
              <li>We do not access your contacts, camera, or microphone</li>
            </ul>
          </div>
        </div>
      </Section>

      {/* ── How we use data ── */}
      <Section title='2. How We Use Your Information'>
        <ul className='list-disc list-inside space-y-2'>
          <li>
            <strong>Newsletter emails:</strong> To send weekly digests about new audit reports,
            budget updates, and economic indicators. We never share your email with third parties.
          </li>
          <li>
            <strong>Account features:</strong> To power your personal watchlist and data alerts.
          </li>
          <li>
            <strong>Analytics:</strong> To improve the platform — for example, understanding which
            county pages are most visited so we prioritise data quality there.
          </li>
        </ul>
      </Section>

      {/* ── Data storage ── */}
      <Section title='3. Where Your Data Is Stored'>
        <p>
          Your data is stored securely in a PostgreSQL database with encryption at rest and in
          transit. Our infrastructure is hosted on industry-standard cloud platforms with data
          centres in secure, audited facilities.
        </p>
        <p>
          Database access is restricted via Row Level Security (RLS) policies. No one — including
          our team — can access your account data without proper authentication.
        </p>
      </Section>

      {/* ── Sharing ── */}
      <Section title='4. Data Sharing'>
        <p>
          <strong>We do not sell, rent, or trade your personal information.</strong> Period.
        </p>
        <p>
          We may share anonymised, aggregate statistics (e.g., &quot;10,000 people visited the
          Nairobi County page this month&quot;) in public reports about platform usage. These
          statistics never identify individuals.
        </p>
      </Section>

      {/* ── Your rights ── */}
      <Section title='5. Your Rights'>
        <div className='bg-gov-sage/5 rounded-xl p-5 border border-gov-sage/10'>
          <p className='mb-3'>You have the right to:</p>
          <ul className='list-disc list-inside space-y-2'>
            <li>
              <strong>Unsubscribe</strong> from the newsletter at any time using the link in every
              email, or via our{' '}
              <Link href='/newsletter/unsubscribe' className='text-gov-sage hover:underline'>
                unsubscribe page
              </Link>
              .
            </li>
            <li>
              <strong>Delete your account</strong> and all associated data by contacting us at{' '}
              <a href='mailto:auditgava@gmail.com' className='text-gov-sage hover:underline'>
                auditgava@gmail.com
              </a>
              .
            </li>
            <li>
              <strong>Request a copy</strong> of any personal data we hold about you.
            </li>
            <li>
              <strong>Correct</strong> any inaccurate information.
            </li>
          </ul>
          <p className='mt-3 text-[13px]'>We will respond to any data request within 14 days.</p>
        </div>
      </Section>

      {/* ── Cookies ── */}
      <Section title='6. Cookies'>
        <p>
          We use <strong>essential cookies only</strong> — specifically for authentication sessions
          (if you create an account). We do not use advertising, marketing, or cross-site tracking
          cookies.
        </p>
      </Section>

      {/* ── Children ── */}
      <Section title="7. Children's Privacy">
        <p>
          AuditGava is a public information platform suitable for all ages. We do not knowingly
          collect personal information from children under 13. If you believe a child has provided
          us with personal data, please contact us and we will delete it promptly.
        </p>
      </Section>

      {/* ── Changes ── */}
      <Section title='8. Changes to This Policy'>
        <p>
          We may update this policy from time to time. Material changes will be announced via our
          newsletter and posted on this page with an updated date. Continued use of the platform
          after changes constitutes acceptance.
        </p>
      </Section>

      {/* ── Contact ── */}
      <Section title='9. Contact Us'>
        <p>
          Questions about this policy? Email{' '}
          <a
            href='mailto:auditgava@gmail.com'
            className='text-gov-sage hover:underline font-medium'>
            auditgava@gmail.com
          </a>
        </p>
      </Section>

      {/* ── Legal links ── */}
      <div className='flex flex-wrap gap-4 pt-2 text-xs text-neutral-muted'>
        <Link href='/about' className='hover:text-gov-sage transition-colors'>
          About
        </Link>
        <Link href='/terms' className='hover:text-gov-sage transition-colors'>
          Terms of Use
        </Link>
      </div>
    </PageShell>
  );
}
