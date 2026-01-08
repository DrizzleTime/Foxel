import { Layout, Flex } from 'antd';
import { memo, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
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
import { AppWindowsProvider, useAppWindows } from '../contexts/AppWindowsContext';
import { AppWindowsLayer } from '../apps/AppWindowsLayer';
import AiAgentWidget from '../components/AiAgentWidget';

const ShellBody = memo(function ShellBody() {
  const params = useParams<{ navKey?: string; '*': string }>();
  const navKey = params.navKey ?? 'files';
  const subPath = params['*'] ?? '';
  const navigate = useNavigate();
  const COLLAPSED_KEY = 'layout.siderCollapsed';
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSED_KEY) === '1');
  const [agentOpen, setAgentOpen] = useState(false);
  useEffect(() => {
    localStorage.setItem(COLLAPSED_KEY, collapsed ? '1' : '0');
  }, [collapsed]);
  const { windows, closeWindow, toggleMax, bringToFront, updateWindow } = useAppWindows();
  const settingsTab = navKey === 'settings' ? (subPath.split('/')[0] || undefined) : undefined;
  const agentCurrentPath = navKey === 'files' ? ('/' + subPath).replace(/\/+/g, '/').replace(/\/+$/, '') || '/' : null;
  return (
    <Layout style={{ minHeight: '100vh', background: 'var(--ant-color-bg-layout)' }}>
      <SideNav
        collapsed={collapsed}
        onToggle={() => setCollapsed(c => !c)}
        activeKey={navKey}
        onChange={(key) => {
          if (key === 'settings') {
            navigate('/settings/appearance', { replace: true });
          } else {
            navigate(`/${key}`);
          }
        }}
      />
      <Layout style={{ background: 'var(--ant-color-bg-layout)' }}>
        <TopHeader collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} onOpenAiAgent={() => setAgentOpen(true)} />
        <Layout.Content style={{ padding: 16, background: 'var(--ant-color-bg-layout)' }}>
          <div style={{ minHeight: 'calc(100vh - 56px - 32px)', background: 'var(--ant-color-bg-layout)' }}>
            <Flex vertical gap={16}>
              {navKey === 'adapters' && <AdaptersPage />}
              {navKey === 'files' && <FileExplorerPage />}
              {navKey === 'share' && <SharePage />}
              {navKey === 'tasks' && <TasksPage />}
              {navKey === 'task-queue' && <TaskQueuePage />}
              {navKey === 'processors' && <ProcessorsPage />}
              {navKey === 'offline' && <OfflineDownloadPage />}
              {navKey === 'plugins' && <PluginsPage />}
              {navKey === 'settings' && (
                <SystemSettingsPage
                  tabKey={settingsTab}
                  onTabNavigate={(key, options) => navigate(`/settings/${key}`, options)}
                />
              )}
              {navKey === 'audit' && <AuditLogsPage />}
              {navKey === 'backup' && <BackupPage />}
            </Flex>
          </div>
        </Layout.Content>
      </Layout>
      {/* 常驻渲染应用窗口（过滤最小化在内部处理） */}
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

const LayoutShell = memo(function LayoutShell() {
  return (
    <AppWindowsProvider>
      <ShellBody />
    </AppWindowsProvider>
  );
});

export default LayoutShell;
