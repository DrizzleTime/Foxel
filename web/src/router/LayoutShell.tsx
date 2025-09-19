import { Layout, Flex } from 'antd';
import { memo, useState } from 'react';
import { useParams, useNavigate } from 'react-router';
import SideNav from '../layout/SideNav.tsx';
import TopHeader from '../layout/TopHeader.tsx';
import FileExplorerPage from '../pages/FileExplorerPage/FileExplorerPage.tsx';
import AdaptersPage from '../pages/AdaptersPage.tsx';
import SharePage from '../pages/SharePage.tsx';
import TasksPage from '../pages/TasksPage.tsx';
import ProcessorsPage from '../pages/ProcessorsPage.tsx';
import OfflineDownloadPage from '../pages/OfflineDownloadPage.tsx';
import SystemSettingsPage from '../pages/SystemSettingsPage/SystemSettingsPage.tsx';
import LogsPage from '../pages/LogsPage.tsx';
import BackupPage from '../pages/SystemSettingsPage/BackupPage.tsx';
import PluginsPage from '../pages/PluginsPage.tsx';
import { AppWindowsProvider, useAppWindows } from '../contexts/AppWindowsContext';
import { AppWindowsLayer } from '../apps/AppWindowsLayer';

const ShellBody = memo(function ShellBody() {
  const { navKey = 'files' } = useParams();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const { windows, closeWindow, toggleMax, bringToFront, updateWindow } = useAppWindows();
  return (
    <Layout style={{ minHeight: '100vh', background: 'var(--ant-color-bg-layout)' }}>
      <SideNav
        collapsed={collapsed}
        onToggle={() => setCollapsed(c => !c)}
        activeKey={navKey}
        onChange={(key) => navigate(`/${key}`)}
      />
      <Layout style={{ background: 'var(--ant-color-bg-layout)' }}>
        <TopHeader collapsed={collapsed} onToggle={() => setCollapsed(c => !c)} />
        <Layout.Content style={{ padding: 16, background: 'var(--ant-color-bg-layout)' }}>
          <div style={{ minHeight: 'calc(100vh - 56px - 32px)', background: 'var(--ant-color-bg-layout)' }}>
            <Flex vertical gap={16}>
              {navKey === 'adapters' && <AdaptersPage />}
              {navKey === 'files' && <FileExplorerPage />}
              {navKey === 'share' && <SharePage />}
              {navKey === 'tasks' && <TasksPage />}
              {navKey === 'processors' && <ProcessorsPage />}
              {navKey === 'offline' && <OfflineDownloadPage />}
              {navKey === 'plugins' && <PluginsPage />}
              {navKey === 'settings' && <SystemSettingsPage />}
              {navKey === 'logs' && <LogsPage />}
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
