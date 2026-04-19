export type Lang = 'zh' | 'en';

const LANG_STORAGE_KEY = 'lang';

export function parseLang(raw: unknown): Lang | null {
  if (typeof raw !== 'string') return null;
  const value = raw.trim().toLowerCase();
  if (!value) return null;
  if (value === 'en' || value.startsWith('en-')) return 'en';
  if (value === 'zh' || value.startsWith('zh-')) return 'zh';
  return null;
}

export function normalizeLang(raw: unknown, fallback: Lang = 'zh'): Lang {
  return parseLang(raw) ?? fallback;
}

export function readStoredLang(): Lang | null {
  if (typeof window === 'undefined') return null;
  try {
    return parseLang(window.localStorage.getItem(LANG_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function persistLang(lang: Lang): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LANG_STORAGE_KEY, lang);
  } catch {
    void 0;
  }
}

export function getActiveLang(fallback: Lang = 'zh'): Lang {
  if (typeof document !== 'undefined') {
    const documentLang = parseLang(document.documentElement.lang);
    if (documentLang) return documentLang;
  }
  return readStoredLang() ?? fallback;
}
