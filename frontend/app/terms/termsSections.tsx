import Link from 'next/link';
import styles from './terms.module.css';

export function Placeholder({ children }: { children: string }) {
  return <mark className={styles.placeholder}>{children}</mark>;
}

// The English review text comes from the approved draft in #l-terms.
// Keep the legal wording intact until the owner and a Kenyan advocate review it.
export const termsSections = [
  {
    id: 'agreement',
    title: 'Agreeing to these terms',
    body: (
      <>
        <p>
          AuditGava (auditgava.com) is run by
          {' '}
          <Placeholder>[full name of person or registered organisation]</Placeholder>
          {' '}
          of
          {' '}
          <Placeholder>[postal address]</Placeholder>
          , Kenya (“AuditGava”, “we”). By using the site you agree to these terms. If you don’t
          agree, please don’t use it. When you create an account or subscribe to our email, we will
          ask you to confirm that you agree.
        </p>
      </>
    ),
  },
  {
    id: 'what-auditgava-is',
    title: 'What AuditGava is',
    body: (
      <>
        <p>
          AuditGava is an independent, free website that republishes and explains public financial
          information about Kenya’s national and county governments, taken from official sources
          such as the Office of the Auditor-General, the Controller of Budget, the National
          Treasury, the Central Bank of Kenya and the Kenya National Bureau of Statistics. We do
          this in the public interest, relying on the rights to freedom of expression and access to
          information in Articles 33 and 35 of the Constitution.
        </p>
        <p>
          We are
          {' '}
          <strong>not</strong>
          {' '}
          a government agency and are not endorsed by any government body. We are not financial,
          legal or investment advisers. We do not support or oppose any political party or
          candidate, and we take no money from parties, candidates or advertisers.
          {' '}
          <Placeholder>[Only keep “nonprofit” if AuditGava is registered as one.]</Placeholder>
        </p>
      </>
    ),
  },
  {
    id: 'accuracy',
    title: 'How we handle accuracy',
    body: (
      <>
        <p>
          Every figure we publish comes from an official document, and we link to it. Where we
          estimate or calculate a figure, we label it as modelled and explain how. Audit findings
          are quoted in the Auditor-General’s own words. An audit finding, including one headed
          “unaccounted for”, is the Auditor-General’s opinion on records and documents. It is not a
          finding that any person committed a crime, and we never present it as one.
        </p>
        <p>
          Official sources sometimes contain errors, disagree with each other, or are revised. We
          show disagreements where we find them. We work hard to be accurate, but we cannot promise
          that every figure is free of error or up to date. Always check the original document
          before relying on a figure for an important decision.
        </p>
      </>
    ),
  },
  {
    id: 'corrections',
    title: 'Corrections and right of reply',
    body: (
      <>
        <p>
          If you believe something on AuditGava is wrong, or you are a person or institution named
          in a finding and want to respond, use the form at
          {' '}
          <Placeholder>[auditgava.com/corrections]</Placeholder>
          {' '}
          or email
          {' '}
          <Placeholder>[corrections@domain]</Placeholder>
          . We will acknowledge you within
          {' '}
          <Placeholder>[2]</Placeholder>
          {' '}
          working days and decide within
          {' '}
          <Placeholder>[7]</Placeholder>
          {' '}
          working days. Corrections are published with the date, and we will publish a fair summary
          of a reply next to the finding it concerns. We follow
          {' '}
          <Placeholder>[the Media Council of Kenya Code of Conduct for the Practice of Journalism]</Placeholder>
          {' '}
          when publishing information about identifiable people.
        </p>
      </>
    ),
  },
  {
    id: 'using-our-content',
    title: 'Using our content',
    body: (
      <>
        <p>
          You may share, quote and republish AuditGava’s figures, charts and explanations, including
          for journalism, research, teaching and advocacy, as long as you:
        </p>
        <ul>
          <li>
            credit “AuditGava” and link to the page you used;
          </li>
          <li>
            don’t change figures or charts in a way that changes their meaning, or remove their
            source lines; and
          </li>
          <li>
            don’t present AuditGava content as official government statistics, or suggest that
            AuditGava endorses you, a party or a candidate.
          </li>
        </ul>
        <p>
          Our own text and charts are licensed under
          {' '}
          <Placeholder>[Creative Commons Attribution 4.0 (CC BY 4.0)]</Placeholder>
          . Government documents remain subject to their own terms; we quote and link them for
          reporting, review and public information. The text of the Constitution is reproduced from
          {' '}
          <Placeholder>[Kenya Law (National Council for Law Reporting)]</Placeholder>
          . The AuditGava name and logo may not be used without permission.
          {' '}
          <Placeholder>[If the code is published under a licence, name it here; otherwise remove any
          “open source” wording.]</Placeholder>
        </p>
      </>
    ),
  },
  {
    id: 'prohibited-use',
    title: 'What you must not do',
    body: (
      <>
        <ul>
          <li>
            Try to get into accounts, systems or data you are not authorised to access, or interfere
            with the site. This may also be an offence under the Computer Misuse and Cybercrimes
            Act.
          </li>
          <li>
            Scrape or call the site in a way that slows it down for others, or ignore rate limits.
          </li>
          <li>
            Upload or send anything unlawful, harmful or that infringes someone else’s rights.
          </li>
          <li>
            Create fake AuditGava graphics or accounts, or alter our content to mislead.
          </li>
          <li>
            Use the site to harass or threaten anyone, including officials named in reports.
          </li>
        </ul>
      </>
    ),
  },
  {
    id: 'accounts',
    title: 'Accounts',
    body: (
      <>
        <p>
          You need to be 18 or older to create an account, or have a parent’s or guardian’s
          permission. Keep your password safe; you are responsible for activity on your account. You
          can delete your account at any time from your Account page. We may suspend an account that
          breaks these terms, and will tell you why unless the law prevents us.
        </p>
      </>
    ),
  },
  {
    id: 'email-digest',
    title: 'Email digest',
    body: (
      <>
        <p>
          Our email digest is free and needs your confirmation. Every email has an unsubscribe link.
          See the
          {' '}
          <Link href='/privacy'>Privacy Policy</Link>
          {' '}
          for how we handle your address.
        </p>
      </>
    ),
  },
  {
    id: 'external-links',
    title: 'Links to other sites',
    body: (
      <>
        <p>
          We link to official documents and other websites. We aren’t responsible for their content
          or availability.
        </p>
      </>
    ),
  },
  {
    id: 'warranty',
    title: 'No warranty',
    body: (
      <>
        <p>
          The site is provided free, “as is” and “as available”. To the extent the law allows, we
          make no promises that it will always be available, error-free or fit for a particular
          purpose.
        </p>
      </>
    ),
  },
  {
    id: 'liability',
    title: 'Limits on our liability',
    body: (
      <>
        <p>
          To the extent the law allows, AuditGava and the people who run it are not liable for any
          indirect or consequential loss, or for any loss arising from reliance on a figure without
          checking the original source. Nothing in these terms limits liability that cannot be
          limited by law, including for fraud or deliberate wrongdoing.
        </p>
      </>
    ),
  },
  {
    id: 'changes',
    title: 'Changes',
    body: (
      <>
        <p>
          We may update these terms. We will post the new version with its effective date and keep
          earlier versions available. If a change materially affects account holders or subscribers,
          we will email them before it takes effect. Continuing to use the site after the effective
          date means you accept the updated terms.
        </p>
      </>
    ),
  },
  {
    id: 'law-and-disputes',
    title: 'Law and disputes',
    body: (
      <>
        <p>
          These terms are governed by the laws of Kenya. If there is a dispute, please contact us
          first so we can try to resolve it. If we can’t, the courts of Kenya have jurisdiction
          <Placeholder>[, with Nairobi as the place of first instance]</Placeholder>
          .
        </p>
      </>
    ),
  },
  {
    id: 'contact',
    title: 'Contact',
    body: (
      <>
        <p>
          <Placeholder>[legal@domain]</Placeholder>
          {' '}
          ·
          {' '}
          <Placeholder>[postal address]</Placeholder>
        </p>
      </>
    ),
  },
];
