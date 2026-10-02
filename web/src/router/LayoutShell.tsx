import { Layout, Flex } from 'antd';
import { memo, useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router';
import type { Location } from 'react-router';
import SideNav from '../layout/SideNav.tsx';
import TopHeader from '../layout/TopHeader.tsx';
import FileExplorerPage from '../pages/FileExplorerPage/FileExplorerPage.tsx';
import AdaptersPage from '../pages/AdaptersPage.tsx';
import SharePage from '../pages/SharePage.tsx';
import TasksPage from '../pages/TasksPage.tsx';
import TaskQueuePage from '../pages/TaskQueuePage.tsx';
import ProcessorsPage from '../pages/ProcessorsPage.tsx';
import OfflineDownloadPage from '../pages/OfflineDownloadPage.tsx';
import SystemSettingsPage from '../pages/SystemSettingsPage/SystemSettingsPage.tsx';
import AuditLogsPage from '../pages/AuditLogsPage.tsx';
import BackupPage from '../pages/SystemSettingsPage/BackupPage.tsx';
import PluginsPage from '../pages/PluginsPage.tsx';
import UsersPage from '../pages/UsersPage/UsersPage.tsx';
import { AppWindowsProvider, useAppWindows } from '../contexts/AppWindowsContext';
import { AppWindowsLayer } from '../apps/AppWindowsLayer';
import AiAgentWidget from '../components/AiAgentWidget';
import useResponsive from '../hooks/useResponsive';

const ShellBody = memo(function ShellBody({ navigationLocation }: { navigationLocation?: Location }) {
  const params = useParams<{ navKey?: string; '*': string }>();
  const navKey = params.navKey ?? 'files';
  const subPath = params['*'] ?? '';
  const navigate = useNavigate();
  const pageLocation = useLocation();
  const location = navigationLocation ?? pageLocation;
  const settingsOpen = /^\/settings(?:\/|$)/.test(location.pathname);
  const { isMobile } = useResponsive();
  const COLLAPSED_KEY = 'layout.siderCollapsed';
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [isMobile, navKey, subPath]);

  const { windows, closeWindow, toggleMax, bringToFront, updateWindow } = useAppWindows();
  const settingsTab = settingsOpen ? location.pathname.split('/')[2] : undefined;
  const handleNavChange = useCallback((key: string) => {
    setMobileNavOpen(false);
    if (key === 'settings') {
      navigate('/settings/appearance', {
        state: { settingsBackground: location },
      });
    } else {
      navigate(`/${key}`);
    }
  }, [location, navigate]);
  const handleSettingsTabNavigate = useCallback((key: string) => {
    navigate(`/settings/${key}`, { replace: true, state: location.state });
  }, [location.state, navigate]);
  const handleCloseSettings = () => {
    const background = location.state?.settingsBackground;
    const target = background && !/^\/settings(?:\/|$)/.test(background.pathname)
      ? background
      : { pathname: '/files' };
    navigate(target, { replace: true, state: background?.state });
  };
  const agentCurrentPath = navKey === 'files' ? ('/' + subPath).replace(/\/+/g, '/').replace(/\/+$/, '') || '/' : null;
  const handleToggleNav = () => {
    if (isMobile) {
      setMobileNavOpen(true);
      return;
    }
    setCollapsed((value) => !value);
  };

  return (
    <Layout style={{ height: '100dvh', overflow: 'hidden', background: 'var(--ant-color-bg-layout)' }}>
      {!isMobile && (
        <SideNav
          collapsed={collapsed}
          onToggle={handleToggleNav}
          activeKey={navKey}
          onChange={handleNavChange}
        />
      )}

      {isMobile && (
        <SideNav
          mobile
          open={mobileNavOpen}
          onClose={() => setMobileNavOpen(false)}
          collapsed={false}
          onToggle={handleToggleNav}
          activeKey={navKey}
          onChange={handleNavChange}
        />
      )}

      <Layout style={{ background: 'var(--ant-color-bg-layout)', minWidth: 0, minHeight: 0, overflow: 'hidden' }}>
        <TopHeader
          collapsed={collapsed}
          onToggle={handleToggleNav}
          onOpenAiAgent={() => setAgentOpen(true)}
          showMenuButton={isMobile || collapsed}
        />
        <Layout.Content
          style={{
            flex: 1,
            padding: isMobile ? 12 : 16,
            background: 'var(--ant-color-bg-layout)',
            display: 'flex',
            flexDirection: 'column',
            minHeight: 0,
            overflow: 'hidden',
          }}
        >
          <div style={{ flex: 1, minHeight: 0, background: 'var(--ant-color-bg-layout)', overflow: 'hidden' }}>
            <Flex vertical style={{ minHeight: 0, height: '100%' }}>
              {navKey === 'adapters' && <AdaptersPage />}
              {navKey === 'files' && <FileExplorerPage />}
              {navKey === 'share' && <SharePage />}
              {navKey === 'tasks' && <TasksPage />}
              {navKey === 'task-queue' && <TaskQueuePage />}
              {navKey === 'processors' && <ProcessorsPage />}
              {navKey === 'offline' && <OfflineDownloadPage />}
              {navKey === 'plugins' && <PluginsPage />}
              {navKey === 'audit' && <AuditLogsPage />}
              {navKey === 'backup' && <BackupPage />}
              {navKey === 'users' && <UsersPage />}
            </Flex>
          </div>
        </Layout.Content>
      </Layout>

      {settingsOpen && (
        <SystemSettingsPage
          tabKey={settingsTab}
          onTabNavigate={handleSettingsTabNavigate}
          onClose={handleCloseSettings}
        />
      )}
      <AppWindowsLayer
        windows={windows}
        onClose={closeWindow}
        onToggleMax={toggleMax}
        onBringToFront={bringToFront}
        onUpdateWindow={updateWindow}
      />
      <AiAgentWidget currentPath={agentCurrentPath} open={agentOpen} onOpenChange={setAgentOpen} />
    </Layout>
  );
});

const LayoutShell = memo(function LayoutShell({ navigationLocation }: { navigationLocation?: Location }) {
  return (
    <AppWindowsProvider>
      <ShellBody navigationLocation={navigationLocation} />
    </AppWindowsProvider>
  );
});

export default LayoutShell;
