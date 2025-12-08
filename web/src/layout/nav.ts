import React from 'react';
import {
  FolderOpenOutlined,
  ApiOutlined,
  ShareAltOutlined,
  CloudDownloadOutlined,
  SettingOutlined,
  RobotOutlined,
  BugOutlined,
  DatabaseOutlined,
  AppstoreOutlined,
  CodeOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';

export interface NavItem { key: string; icon: ReactNode; label: string; }
export interface NavGroup { key: string; title?: string; children: NavItem[]; }

export const navGroups: NavGroup[] = [
  {
    key: 'library',
    title: '',
    children: [
      { key: 'files', icon: React.createElement(FolderOpenOutlined), label: 'All Files' },
    ]
  },
  {
    key: 'manage',
    title: 'Manage',
    children: [
      { key: 'processors', icon: React.createElement(CodeOutlined), label: 'Processors' },
      { key: 'tasks', icon: React.createElement(RobotOutlined), label: 'Automation' },
      { key: 'task-queue', icon: React.createElement(ClockCircleOutlined), label: 'Task Queue' },
      { key: 'share', icon: React.createElement(ShareAltOutlined), label: 'My Shares' },
      { key: 'offline', icon: React.createElement(CloudDownloadOutlined), label: 'Offline Downloads' },
      { key: 'adapters', icon: React.createElement(ApiOutlined), label: 'Adapters' },
      { key: 'plugins', icon: React.createElement(AppstoreOutlined), label: 'Plugins' },
    ]
  },
  {
    key: 'system',
    title: 'System',
    children: [
      { key: 'settings', icon: React.createElement(SettingOutlined), label: 'System Settings' },
      { key: 'backup', icon: React.createElement(DatabaseOutlined), label: 'Backup & Restore' },
      { key: 'audit', icon: React.createElement(BugOutlined), label: 'Audit Logs' }
    ]
  }
];

export const primaryNav: NavItem[] = navGroups.flatMap(g => g.children);
