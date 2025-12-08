import { createContext, useContext, useMemo, useState, useEffect } from 'react';
import type { PropsWithChildren } from 'react';
import en from './locales/en.json';
import zhOverrides from './locales/zh.json';

type Lang = 'zh' | 'en';
type Dict = Record<string, string>;

const dicts: Record<Lang, Dict> = {
  en,
  zh: { ...en, ...zhOverrides },
};

export interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
}

export function I18nProvider({ children }: PropsWithChildren) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem('lang') as Lang) || 'zh');

  const setLang = (l: Lang) => {
    setLangState(l);
    localStorage.setItem('lang', l);
  };

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  const t = (key: string, params?: Record<string, string | number>) => {
    const dict = dicts[lang] || {};
    const raw = dict[key] ?? key; // fallback to key (English)
    return interpolate(raw, params);
  };

  const value = useMemo<I18nContextValue>(() => ({ lang, setLang, t }), [lang]);

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
