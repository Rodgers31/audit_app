/**
 * Three-way language toggle scaffolding: English (default), Swahili, or
 * a deliberately plain-language English for readers who find "fiscal
 * absorption" etc. off-putting.
 *
 * This is a prototype — only the most visible hero/nav strings are
 * translated so far. The pattern (`t('home.hero.title')`) extends
 * naturally to the rest of the app as we fill in entries.
 *
 * Persistence: localStorage keyed on 'auditgava-lang'. We read after
 * hydration to avoid server/client markup mismatches.
 */
'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { MESSAGES, type Lang, type TranslationKey } from './messages';

interface LangContextValue {
  lang: Lang;
  setLang: (next: Lang) => void;
  t: (key: TranslationKey, fallback?: string) => string;
  /** Null until hydration completes — components that care about avoiding
   *  flash-of-wrong-language can check this. */
  ready: boolean;
}

const LangContext = createContext<LangContextValue | null>(null);

const STORAGE_KEY = 'auditgava-lang';

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>('en');
  const [ready, setReady] = useState(false);

  // Hydrate from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === 'en' || stored === 'sw' || stored === 'plain') {
        setLangState(stored);
      }
    } catch {
      // localStorage may be blocked — fall back to default 'en'
    }
    setReady(true);
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const t = useCallback(
    (key: TranslationKey, fallback?: string): string => {
      const entry = MESSAGES[key];
      if (!entry) return fallback ?? key;
      // Fall back to English if the chosen language doesn't have a string yet
      return entry[lang] || entry.en || fallback || key;
    },
    [lang]
  );

  const value = useMemo<LangContextValue>(
    () => ({ lang, setLang, t, ready }),
    [lang, setLang, t, ready]
  );

  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) {
    // Render-time fallback: if a component renders outside the provider
    // (e.g. server component boundary), return a no-op translator rather
    // than throw. Keeps the prototype from crashing during incremental
    // rollout.
    return {
      lang: 'en',
      setLang: () => {},
      t: (k, fallback) => fallback ?? MESSAGES[k]?.en ?? k,
      ready: false,
    };
  }
  return ctx;
}
