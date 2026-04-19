import { useState, useEffect } from 'react';
import { AppRouter } from './router/index.tsx';
import { AuthProvider } from './contexts/AuthContext.tsx';
import { status as getStatus } from './api/config.ts';
import type { SystemStatus } from './api/config.ts';
import { SystemContext } from './contexts/SystemContext.tsx';
import { ThemeProvider } from './contexts/ThemeContext.tsx';
import { Spin } from 'antd';
import { Routes, Route, Navigate } from 'react-router';
import SetupPage from './pages/SetupPage.tsx';
import { I18nProvider } from './i18n';

function AppInner({ status }: { status: SystemStatus }) {
  return (
    <SystemContext.Provider value={status}>
      <AuthProvider>
        <ThemeProvider>
          {!status.is_initialized ? (
            <Routes>
              <Route path="/setup" element={<SetupPage />} />
              <Route path="*" element={<Navigate to="/setup" replace />} />
            </Routes>
          ) : (
            <AppRouter />
          )}
        </ThemeProvider>
      </AuthProvider>
    </SystemContext.Provider>
  );
}

export default function App() {
  const [status, setStatus] = useState<SystemStatus | null>(null);

  useEffect(() => {
    async function checkInitialization() {
      try {
        const nextStatus = await getStatus();
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
      } catch (error) {
        console.error("Failed to check initialization status:", error);
      }
    }
    checkInitialization();
  }, []);

  if (status === null) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <I18nProvider defaultLanguage={status.default_language}>
      <AppInner status={status} />
    </I18nProvider>
  );
}
