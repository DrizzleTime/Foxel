import { Layout, Flex, Modal, theme } from 'antd';
import { lazy, memo, Suspense, useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import SideNav from '../layout/SideNav.tsx';
import TopHeader from '../layout/TopHeader.tsx';
import { primaryNav } from '../layout/nav';
import { AppWindowsProvider, useAppWindows } from '../contexts/AppWindowsContext';
import { AppWindowsLayer } from '../apps/AppWindowsLayer';
import PageLoading from '../components/PageLoading';
import AiAgentDrawer from '../components/AiAgentDrawer';
import useResponsive from '../hooks/useResponsive';
import { useI18n } from '../i18n';

const FileExplorerPage = lazy(() => import('../pages/FileExplorerPage/FileExplorerPage.tsx'));
const AdaptersPage = lazy(() => import('../pages/AdaptersPage.tsx'));
const SharePage = lazy(() => import('../pages/SharePage.tsx'));
const TasksPage = lazy(() => import('../pages/TasksPage.tsx'));
const TaskQueuePage = lazy(() => import('../pages/TaskQueuePage.tsx'));
const ProcessorsPage = lazy(() => import('../pages/ProcessorsPage.tsx'));
const OfflineDownloadPage = lazy(() => import('../pages/OfflineDownloadPage.tsx'));
const SystemSettingsPage = lazy(() => import('../pages/SystemSettingsPage/SystemSettingsPage.tsx'));
const AuditLogsPage = lazy(() => import('../pages/AuditLogsPage.tsx'));
const BackupPage = lazy(() => import('../pages/SystemSettingsPage/BackupPage.tsx'));
const PluginsPage = lazy(() => import('../pages/PluginsPage.tsx'));
const UsersPage = lazy(() => import('../pages/UsersPage/UsersPage.tsx'));
const AiAgentWidget = lazy(() => import('../components/AiAgentWidget'));

const ShellBody = memo(function ShellBody() {
  const params = useParams<{ navKey?: string; '*': string }>();
  const navKey = params.navKey ?? 'files';
  const subPath = params['*'] ?? '';
  const navigate = useNavigate();
  const { isMobile } = useResponsive();
  const { token } = theme.useToken();
  const { t } = useI18n();
  const COLLAPSED_KEY = 'layout.siderCollapsed';
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentMounted, setAgentMounted] = useState(false);
  const [resourceVersions, setResourceVersions] = useState({ adapters: 0, tasks: 0 });
  const handleResourceCreated = useCallback((resource: 'adapters' | 'tasks') => {
    setResourceVersions((previous) => ({ ...previous, [resource]: previous[resource] + 1 }));
  }, []);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const agentWidth = isMobile ? '100vw' : 'clamp(320px, 32vw, 480px)';

  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  useEffect(() => {
    setMobileNavOpen(false);
  }, [isMobile, navKey, subPath]);

  const { windows, closeWindow, toggleMax, bringToFront, updateWindow } = useAppWindows();
  const handleNavChange = useCallback((key: string) => {
    setMobileNavOpen(false);
    if (key === 'settings') {
      setSettingsOpen(true);
    } else {
      navigate(`/${key}`);
    }
  }, [navigate]);
  const agentCurrentPath = navKey === 'files' ? ('/' + subPath).replace(/\/+/g, '/').replace(/\/+$/, '') || '/' : null;
  const agentCurrentPage = primaryNav.find((item) => item.key === navKey);
  const handleToggleNav = () => {
    if (isMobile) {
      setMobileNavOpen(true);
      return;
    }
    setCollapsed((value) => !value);
    window.requestAnimationFrame(() => document.querySelector<HTMLElement>('[data-nav-toggle]')?.focus());
  };

  return (
    <Layout style={{
      height: '100dvh',
      overflow: 'hidden',
      background: 'var(--ant-color-bg-layout)',
      paddingRight: agentOpen && !isMobile ? agentWidth : 0,
      transition: `padding-right ${token.motionDurationSlow} ${token.motionEaseInOut}`,
    }}>
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
          onOpenAiAgent={() => {
            setAgentMounted(true);
            setAgentOpen(true);
          }}
          showMenuButton={isMobile || collapsed}
          menuExpanded={isMobile ? mobileNavOpen : !collapsed}
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
              <Suspense fallback={<PageLoading />}>
                {navKey === 'adapters' && <AdaptersPage refreshVersion={resourceVersions.adapters} />}
                {navKey === 'files' && <FileExplorerPage />}
                {navKey === 'share' && <SharePage />}
                {navKey === 'tasks' && <TasksPage refreshVersion={resourceVersions.tasks} />}
                {navKey === 'task-queue' && <TaskQueuePage />}
                {navKey === 'processors' && <ProcessorsPage />}
                {navKey === 'offline' && <OfflineDownloadPage />}
                {navKey === 'plugins' && <PluginsPage />}
                {navKey === 'audit' && <AuditLogsPage />}
                {navKey === 'backup' && <BackupPage />}
                {navKey === 'users' && <UsersPage />}
              </Suspense>
            </Flex>
          </div>
        </Layout.Content>
      </Layout>

      {settingsOpen && (
        <Suspense fallback={(
          <Modal
            title={t('System Settings')}
            open
            onCancel={() => setSettingsOpen(false)}
            width={isMobile ? 'calc(100vw - 24px)' : 1180}
            style={{ maxWidth: 'calc(100vw - 24px)' }}
            centered
            footer={null}
          >
            <PageLoading />
          </Modal>
        )}>
          <SystemSettingsPage onClose={() => setSettingsOpen(false)} />
        </Suspense>
      )}
      <AppWindowsLayer
        windows={windows}
        onClose={closeWindow}
        onToggleMax={toggleMax}
        onBringToFront={bringToFront}
        onUpdateWindow={updateWindow}
      />
      {agentMounted && (
        <Suspense fallback={(
          <AiAgentDrawer
            open={agentOpen}
            onClose={() => setAgentOpen(false)}
            width={agentWidth}
          >
            <PageLoading />
          </AiAgentDrawer>
        )}>
          <AiAgentWidget
            currentPath={agentCurrentPath}
            currentPage={agentCurrentPage && { key: agentCurrentPage.key, label: t(agentCurrentPage.label), icon: agentCurrentPage.icon }}
            onResourceCreated={handleResourceCreated}
            open={agentOpen}
            onOpenChange={setAgentOpen}
            width={agentWidth}
          />
        </Suspense>
      )}
    </Layout>
  );
});

const LayoutShell = memo(function LayoutShell() {
  return (
    <AppWindowsProvider>
      <ShellBody />
    </AppWindowsProvider>
  );
});

export default LayoutShell;
