'use client';

import PageShell from '@/components/layout/PageShell';
import { FileText } from 'lucide-react';
import Link from 'next/link';

const LAST_UPDATED = 'March 1, 2026';

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className='space-y-3'>
      <h2 className='font-display text-xl text-neutral-text'>{title}</h2>
      <div className='text-neutral-muted text-[14px] leading-[1.75] space-y-3'>{children}</div>
    </section>
  );
}

export default function TermsPage() {
  return (
    <PageShell title='Terms of Use' subtitle='The rules of the road for using AuditGava'>
      {/* Last updated badge */}
      <div className='flex items-center gap-3 -mt-1'>
        <div className='w-9 h-9 rounded-lg bg-gov-sage/15 flex items-center justify-center border border-gov-sage/20'>
          <FileText className='w-[18px] h-[18px] text-gov-sage' />
        </div>
        <span className='text-xs text-neutral-muted'>
          Last updated: <strong className='text-neutral-text'>{LAST_UPDATED}</strong>
        </span>
      </div>

      {/* ── Acceptance ── */}
      <Section title='1. Acceptance of Terms'>
        <p>
          By accessing or using AuditGava (&quot;the platform&quot;), you agree to these Terms of
          Use. If you do not agree, please do not use the platform. We may update these terms at any
          time — continued use after changes constitutes acceptance.
        </p>
      </Section>

      {/* ── What we are ── */}
      <Section title='2. About the Platform'>
        <p>
          AuditGava is a <strong>free, non-commercial, civic technology platform</strong> that
          aggregates publicly available government financial data from official Kenyan sources. We
          are a nonprofit initiative focused on transparency and accountability.
        </p>
        <p>
          We are <strong>not</strong> a government agency, financial advisor, or legal authority.
          The platform is an independent civic project.
        </p>
      </Section>

      {/* ── Data accuracy ── */}
      <Section title='3. Data Accuracy'>
        <div className='bg-gov-gold/5 rounded-xl p-5 border border-gov-gold/15'>
          <p>
            We make every effort to present accurate, up-to-date data sourced from official
            government publications including the Office of the Auditor General, Controller of
            Budget, Kenya National Bureau of Statistics, and the National Treasury.
          </p>
          <p className='mt-2'>
            However, <strong>we cannot guarantee that all data is error-free</strong>. Source data
            may contain errors from the original government publications, ETL processing delays may
            cause temporary gaps, and figures may be updated or revised by the originating agencies
            after we publish them.
          </p>
          <p className='mt-2'>
            If you spot an inaccuracy, please{' '}
            {/* <a
              href='https://github.com/Rodgers31/audit_app/issues'
              target='_blank'
              rel='noopener noreferrer'
              className='text-gov-sage hover:underline font-medium'>
              report it on GitHub
            </a>{' '} */}
            email{' '}
            <a
              href='mailto:auditgava@gmail.com'
              className='text-gov-sage hover:underline font-medium'>
              auditgava@gmail.com
            </a>
            .
          </p>
        </div>
      </Section>

      {/* ── Permitted use ── */}
      <Section title='4. Permitted Use'>
        <p>You are welcome to use AuditGava to:</p>
        <ul className='list-disc list-inside space-y-1'>
          <li>Research and understand Kenya&apos;s public finances</li>
          <li>Share data, charts, and insights with proper attribution</li>
          <li>Use data for journalism, academic research, or advocacy</li>
          {/* <li>Build upon our open-source code (see our GitHub license)</li> */}
        </ul>
        <p className='mt-2'>
          We encourage the widest possible use of this data for civic purposes.
        </p>
      </Section>

      {/* ── Prohibited use ── */}
      <Section title='5. Prohibited Use'>
        <p>You may not:</p>
        <ul className='list-disc list-inside space-y-1'>
          <li>Misrepresent data from this platform as official government statistics</li>
          <li>Use automated scraping in a way that degrades platform performance for others</li>
          <li>Attempt to gain unauthorised access to accounts or backend systems</li>
          <li>Use the platform for any unlawful purpose</li>
          <li>Remove or obscure attribution when sharing AuditGava data</li>
        </ul>
      </Section>

      {/* ── Accounts ── */}
      <Section title='6. User Accounts'>
        <p>
          Some features (watchlist, data alerts) require creating an account. You are responsible
          for keeping your credentials secure. We reserve the right to suspend accounts that violate
          these terms.
        </p>
        <p>
          You may delete your account at any time by contacting{' '}
          <a href='mailto:auditgava@gmail.com' className='text-gov-sage hover:underline'>
            auditgava@gmail.com
          </a>
          . We will remove all associated personal data within 14 days.
        </p>
      </Section>

      {/* ── Intellectual property ── */}
      <Section title='7. Intellectual Property'>
        <p>
          The AuditGava platform code is open source. The underlying government data is public
          information belonging to the Republic of Kenya.
        </p>
        <p>
          The AuditGava name, logo, and original content (explanatory text, educational materials,
          visualisation designs) are the property of the AuditGava project and may not be used to
          imply endorsement without permission.
        </p>
      </Section>

      {/* ── Disclaimer ── */}
      <Section title='8. Disclaimer of Warranties'>
        <div className='bg-white dark:bg-surface-base rounded-xl p-5 border border-neutral-border shadow-surface'>
          <p>
            AuditGava is provided <strong>&quot;as is&quot;</strong> and{' '}
            <strong>&quot;as available&quot;</strong> without warranties of any kind, either express
            or implied. We do not warrant that the platform will be uninterrupted, error-free, or
            free of harmful components.
          </p>
          <p className='mt-2'>
            <strong>
              Do not rely on AuditGava data as the sole basis for financial, legal, or investment
              decisions.
            </strong>{' '}
            Always verify critical data against original government publications.
          </p>
        </div>
      </Section>

      {/* ── Liability ── */}
      <Section title='9. Limitation of Liability'>
        <p>
          To the fullest extent permitted by law, AuditGava and its contributors shall not be liable
          for any indirect, incidental, special, consequential, or punitive damages arising from
          your use of the platform, even if we have been advised of the possibility of such damages.
        </p>
      </Section>

      {/* ── Governing law ── */}
      <Section title='10. Governing Law'>
        <p>
          These terms are governed by the laws of the Republic of Kenya. Any disputes shall be
          resolved through the courts of Kenya, with Nairobi as the jurisdiction of first instance.
        </p>
      </Section>

      {/* ── Contact ── */}
      <Section title='11. Contact'>
        <p>
          Questions about these terms? Email{' '}
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
        <Link href='/privacy' className='hover:text-gov-sage transition-colors'>
          Privacy Policy
        </Link>
      </div>
    </PageShell>
  );
}
