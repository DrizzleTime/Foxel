import { lazy, Suspense, useState, useEffect, useCallback } from 'react';
import { AppRouter } from './router/index.tsx';
import { AuthProvider } from './contexts/AuthContext.tsx';
import { status as getStatus } from './api/config.ts';
import type { SystemStatus } from './api/config.ts';
import { SystemContext } from './contexts/SystemContext.tsx';
import { ThemeProvider } from './contexts/ThemeContext.tsx';
import { Button, ConfigProvider, Flex, Typography } from 'antd';
import { Routes, Route, Navigate } from 'react-router';
import PageLoading from './components/PageLoading';
import { I18nProvider, useI18n } from './i18n';
import baseTheme from './theme';

const SetupPage = lazy(() => import('./pages/SetupPage.tsx'));

function StartupStatus({ failed, onRetry }: { failed: boolean; onRetry: () => void }) {
  const { t } = useI18n();
  if (!failed) return <PageLoading fullPage />;
  return (
    <Flex component="main" vertical align="center" justify="center" gap={16} style={{ minHeight: '100dvh', padding: 24, textAlign: 'center' }}>
      <div role="alert">
        <Typography.Title level={1} style={{ fontSize: 24 }}>{t('Unable to load Foxel')}</Typography.Title>
        <Typography.Paragraph>{t('Check your connection and try again.')}</Typography.Paragraph>
      </div>
      <Button type="primary" onClick={onRetry}>{t('Retry')}</Button>
    </Flex>
  );
}

function AppInner({ status }: { status: SystemStatus }) {
  return (
    <SystemContext.Provider value={status}>
      <AuthProvider>
        <ThemeProvider>
          <Suspense fallback={<PageLoading fullPage />}>
            {!status.is_initialized ? (
              <Routes>
                <Route path="/setup" element={<SetupPage />} />
                <Route path="*" element={<Navigate to="/setup" replace />} />
              </Routes>
            ) : (
              <AppRouter />
            )}
          </Suspense>
        </ThemeProvider>
      </AuthProvider>
    </SystemContext.Provider>
  );
}

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [statusError, setStatusError] = useState(false);

  const checkInitialization = useCallback(async () => {
    setStatusError(false);
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 15000);
    try {
      const nextStatus = await getStatus(controller.signal);
      setStatus(nextStatus);
      document.title = nextStatus.title;
      let favicon = document.querySelector("link[rel*='icon']") as HTMLLinkElement | null;
      if (!favicon) {
        favicon = document.createElement('link');
        favicon.rel = 'icon';
        document.head.appendChild(favicon);
      }
      if (favicon) {
        favicon.href = nextStatus.favicon || nextStatus.logo;
      }
    } catch {
      setStatusError(true);
    } finally {
      window.clearTimeout(timer);
    }
  }, []);

  useEffect(() => { void checkInitialization(); }, [checkInitialization]);

  if (status === null) {
    return (
      <I18nProvider>
        <ConfigProvider theme={{ ...baseTheme, cssVar: {} }}>
          <StartupStatus failed={statusError} onRetry={() => { void checkInitialization(); }} />
        </ConfigProvider>
      </I18nProvider>
    );
  }

  return (
    <I18nProvider defaultLanguage={status.default_language}>
      <AppInner status={status} />
    </I18nProvider>
  );
}
