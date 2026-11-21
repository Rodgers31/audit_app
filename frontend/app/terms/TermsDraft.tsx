'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { useLang } from '@/lib/i18n/LangProvider';
import { termsMessages } from './messages';
import { Placeholder, termsSections } from './termsSections';
import styles from './terms.module.css';

const summary = [
  'AuditGava is free and independent.',
  'Check the source before relying on a figure.',
  'Credit AuditGava and keep the source lines.',
  'Delete your account from your Account page.',
  'See how to ask for a correction or reply.',
];

export function TermsDraft() {
  const { lang } = useLang();
  const copy = (key: keyof typeof termsMessages) => termsMessages[key][lang];
  const [currentSection, setCurrentSection] = useState(termsSections[0].id);

  useEffect(() => {
    function updateSection() {
      const anchor = window.location.hash.slice(1);
      const section = termsSections.find(({ id }) => id === anchor);
      setCurrentSection(section?.id ?? termsSections[0].id);
    }
    updateSection();
    window.addEventListener('hashchange', updateSection);
    return () => window.removeEventListener('hashchange', updateSection);
  }, []);

  return (
    <div className='bg-gov-sand pt-[var(--public-header-height)] text-neutral-text dark:bg-surface-sunken'>
      <div data-terms-draft className={styles.layout}>
        <header className={styles.header}>
          <div className={styles.titleBand}>
            <h1 className='audit-figure text-audit-title uppercase'>{copy('title')}</h1>
          </div>
          <div className={styles.metadata}>
            <dl>
              <div>
                <dt>{copy('updated')}</dt>
                <dd><Placeholder>[last updated date]</Placeholder></dd>
              </div>
              <div>
                <dt>{copy('effective')}</dt>
                <dd><Placeholder>[date]</Placeholder></dd>
              </div>
              <div>
                <dt>{copy('version')}</dt>
                <dd><Placeholder>[2.0]</Placeholder></dd>
              </div>
            </dl>
            <Link className={styles.link} href='/terms/2026-03-01'>
              {copy('previousVersion')} <span aria-hidden='true'>›</span>
            </Link>
          </div>
        </header>

        <div className={styles.intro}>
          <p className={styles.draftNotice}>
            <strong>{copy('draft')}</strong>
            {' '}
            {copy('review')}
          </p>
          {lang === 'sw' && <p className='text-sm'>{copy('englishDraft')}</p>}

          <section aria-labelledby='terms-summary' className={styles.summary}>
            <h2 id='terms-summary'>{copy('shortVersion')}</h2>
            <ul lang='en'>
              {summary.map((point) => <li key={point}>{point}</li>)}
            </ul>
            <p>{copy('readInFull')}</p>
          </section>
        </div>

        <nav aria-labelledby='terms-contents' className={styles.contents}>
          <h2 id='terms-contents'>{copy('contents')}</h2>
          <ol lang='en'>
            {termsSections.map(({ id, title }, index) => (
              <li key={id}>
                <a href={`#${id}`} aria-current={id === currentSection ? 'location' : undefined}>
                  <span>{index + 1}. {title}</span>
                  <span aria-hidden='true'>›</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article aria-labelledby='terms-full-text' className={styles.article} lang='en'>
          <h2 id='terms-full-text' className='sr-only'>Full draft of the Terms of Use</h2>
          {termsSections.map(({ id, title, body }, index) => (
            <section key={id}>
              <h3 id={id} tabIndex={-1}>{index + 1}. {title}</h3>
              {body}
            </section>
          ))}
          <div className={styles.related} lang={lang === 'sw' ? 'sw' : 'en'}>
            <Link href='/about' className={styles.link}>{copy('about')}</Link>
            <Link href='/privacy' className={styles.link}>{copy('privacy')}</Link>
          </div>
        </article>
      </div>
    </div>
  );
}
