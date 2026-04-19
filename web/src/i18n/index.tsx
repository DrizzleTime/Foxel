import { createContext, useCallback, useContext, useMemo, useState, useEffect } from 'react';
import type { PropsWithChildren } from 'react';
import en from './locales/en.json';
import zhOverrides from './locales/zh.json';
import { normalizeLang, persistLang, readStoredLang, type Lang } from './lang';

type Dict = Record<string, string>;

const dicts: Record<Lang, Dict> = {
  en,
  zh: { ...en, ...zhOverrides },
};

interface SetLangOptions {
  persist?: boolean;
}

export interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang, options?: SetLangOptions) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
}

interface I18nProviderProps {
  defaultLanguage?: Lang;
}

export function I18nProvider({ children, defaultLanguage }: PropsWithChildren<I18nProviderProps>) {
  const fallbackLang = normalizeLang(defaultLanguage, 'zh');
  const [lang, setLangState] = useState<Lang>(() => readStoredLang() ?? fallbackLang);

  const setLang = useCallback((nextLang: Lang, options?: SetLangOptions) => {
    const normalized = normalizeLang(nextLang, fallbackLang);
    setLangState(normalized);
    if (options?.persist === false) return;
    persistLang(normalized);
  }, [fallbackLang]);

  useEffect(() => {
    if (!readStoredLang()) {
      setLangState(fallbackLang);
    }
  }, [fallbackLang]);

  useEffect(() => {
    document.documentElement.lang = lang;
    window.dispatchEvent(new CustomEvent('foxel:langchange', { detail: { lang } }));
  }, [lang]);

  const t = useCallback((key: string, params?: Record<string, string | number>) => {
    const dict = dicts[lang] || {};
    const raw = dict[key] ?? key; // fallback to key (English)
    return interpolate(raw, params);
  }, [lang]);

  const value = useMemo<I18nContextValue>(() => ({ lang, setLang, t }), [lang, setLang, t]);

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within I18nProvider');
  return ctx;
}
