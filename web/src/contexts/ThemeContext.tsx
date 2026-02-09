import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ConfigProvider, theme as antdTheme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import enUS from 'antd/locale/en_US';
import type { ThemeConfig } from 'antd/es/config-provider/context';
import { getPublicConfig } from '../api/config';
import { useAuth } from './AuthContext';
import baseTheme from '../theme';
import { useI18n } from '../i18n';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeState {
  mode: ThemeMode;
  primaryColor?: string | null;
  borderRadius?: number | null;
  customTokens?: Record<string, any> | null;
  customCSS?: string | null;
}

interface ThemeContextType {
  refreshTheme: () => Promise<void>;
  previewTheme: (patch: Partial<ThemeState>) => void;
  mode: ThemeMode;
  resolvedMode: ThemeMode;
}

const Ctx = createContext<ThemeContextType>({} as any);

const CONFIG_KEYS = {
  MODE: 'THEME_MODE',
  PRIMARY: 'THEME_PRIMARY_COLOR',
  RADIUS: 'THEME_BORDER_RADIUS',
  TOKENS: 'THEME_CUSTOM_TOKENS',
  CSS: 'THEME_CUSTOM_CSS',
};

function parseJSON<T = any>(text: string | null | undefined): T | null {
  if (!text) return null;
  try {
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

function useSystemDarkPreferred() {
  const [isDark, setIsDark] = useState<boolean>(
    typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia('(prefers-color-scheme: dark)').matches
      : false
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (e: MediaQueryListEvent) => setIsDark(e.matches);
    mql.addEventListener?.('change', handler);
    return () => mql.removeEventListener?.('change', handler);
  }, []);
  return isDark;
}

function buildThemeConfig(state: ThemeState, systemDark: boolean): ThemeConfig {
  const resolvedMode: ThemeMode = state.mode === 'system' ? (systemDark ? 'dark' : 'light') : state.mode;
  const algorithm = resolvedMode === 'dark'
    ? [antdTheme.darkAlgorithm, antdTheme.compactAlgorithm]
    : [antdTheme.defaultAlgorithm, antdTheme.compactAlgorithm];

  const safeBaseTokens: Record<string, any> = resolvedMode === 'dark'
    ? {
        borderRadius: baseTheme.token?.borderRadius,
        fontSize: baseTheme.token?.fontSize,
        controlHeight: baseTheme.token?.controlHeight,
        boxShadow: baseTheme.token?.boxShadow,
      }
    : { ...(baseTheme.token as any) };

  const token = {
    ...safeBaseTokens,
    ...(state.primaryColor ? { colorPrimary: state.primaryColor } : {}),
    ...(state.borderRadius != null ? { borderRadius: state.borderRadius } : {}),
    ...(state.customTokens || {}),
  } as any;

  const baseComponents = { ...(baseTheme.components as any) };
  if (resolvedMode === 'dark' && baseComponents) {
    if (baseComponents.Menu) {
      const rest = { ...baseComponents.Menu };
      delete rest.itemHoverColor;
      delete rest.itemHoverBg;
      delete rest.itemSelectedBg;
      delete rest.itemSelectedColor;
      baseComponents.Menu = rest;
    }
    if (baseComponents.Dropdown) {
      const rest = { ...baseComponents.Dropdown };
      delete rest.controlItemBgHover;
      baseComponents.Dropdown = rest;
    }
    if (baseComponents.Table) {
      const rest = { ...baseComponents.Table };
      delete rest.headerBg;
      delete rest.rowHoverBg;
      baseComponents.Table = rest;
    }
  }

  return { algorithm, token, components: baseComponents } satisfies ThemeConfig;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuth();
  const { lang } = useI18n();
  const systemDark = useSystemDarkPreferred();
  const [state, setState] = useState<ThemeState>({ mode: 'light' });
  const stateRef = useRef(state);
  const styleTagRef = useRef<HTMLStyleElement | null>(null);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  const ensureStyleTag = useCallback(() => {
    if (styleTagRef.current) return styleTagRef.current;
    let styleEl = document.getElementById('foxel-custom-css') as HTMLStyleElement | null;
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = 'foxel-custom-css';
      document.head.appendChild(styleEl);
    }
    styleTagRef.current = styleEl;
    return styleEl;
  }, []);

  const applyCustomCSS = useCallback((cssText: string | null | undefined) => {
    const el = ensureStyleTag();
    el.textContent = cssText || '';
  }, [ensureStyleTag]);

  const applyHtmlDataTheme = useCallback((mode: ThemeMode) => {
    const finalMode = mode === 'system' ? (systemDark ? 'dark' : 'light') : mode;
    document.documentElement.setAttribute('data-theme', finalMode);
  }, [systemDark]);

  const refreshTheme = useCallback(async () => {
    if (!isAuthenticated) {
      applyHtmlDataTheme(stateRef.current.mode || 'light');
      applyCustomCSS(stateRef.current.customCSS || '');
      return;
    }
    try {
      const cfg = await getPublicConfig();
      const mode = (cfg[CONFIG_KEYS.MODE] as ThemeMode) || 'light';
      const primary = (cfg[CONFIG_KEYS.PRIMARY] as string) || null;
      const radiusStr = cfg[CONFIG_KEYS.RADIUS];
      const radius = radiusStr != null ? Number(radiusStr) : null;
      const customTokens = parseJSON<Record<string, any>>(cfg[CONFIG_KEYS.TOKENS]);
      const customCSS = (cfg[CONFIG_KEYS.CSS] as string) || '';
      setState({ mode, primaryColor: primary, borderRadius: radius, customTokens, customCSS });
      applyHtmlDataTheme(mode);
      applyCustomCSS(customCSS);
    } catch {
      applyHtmlDataTheme('light');
      applyCustomCSS('');
    }
  }, [applyCustomCSS, applyHtmlDataTheme, isAuthenticated]);

  const previewTheme = useCallback((patch: Partial<ThemeState>) => {
    const next: ThemeState = { ...stateRef.current, ...patch };
    stateRef.current = next;
    setState(next);
    applyHtmlDataTheme(next.mode || 'light');
    applyCustomCSS(next.customCSS || '');
  }, [applyCustomCSS, applyHtmlDataTheme]);

  useEffect(() => {
    void refreshTheme();
  }, [refreshTheme]);

  const themeConfig = useMemo(() => buildThemeConfig(state, systemDark), [state, systemDark]);
  const resolvedMode: ThemeMode = useMemo(() => (state.mode === 'system' ? (systemDark ? 'dark' : 'light') : state.mode), [state.mode, systemDark]);
  const locale = useMemo(() => (lang === 'zh' ? zhCN : enUS), [lang]);

  const ctxValue = useMemo<ThemeContextType>(() => ({
    refreshTheme,
    previewTheme,
    mode: state.mode,
    resolvedMode,
  }), [previewTheme, refreshTheme, resolvedMode, state.mode]);

  return (
    <Ctx.Provider value={ctxValue}>
      <ConfigProvider theme={{ ...themeConfig, cssVar: {} }} locale={locale}>
        {children}
      </ConfigProvider>
    </Ctx.Provider>
  );
}

export function useTheme() {
  return useContext(Ctx);
}
