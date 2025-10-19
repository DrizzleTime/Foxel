import React from 'react';
import { Table, Dropdown, Button, Tooltip, theme } from 'antd';
import { FolderFilled, MoreOutlined, EditOutlined, DeleteOutlined, AppstoreOutlined, FolderOpenOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../api/client';
import { getFileIcon } from './FileIcons';
import { getAppsForEntry, getDefaultAppForEntry } from '../../../apps/registry';
import { useTheme } from '../../../contexts/ThemeContext';
import { useI18n } from '../../../i18n';

interface FileListViewProps {
  entries: VfsEntry[];
  selectedEntries: string[];
  onRowClick: (entry: VfsEntry, e: React.MouseEvent) => void;
  onSelectionChange: (selectedKeys: string[]) => void;
  onOpen: (entry: VfsEntry) => void;
  onOpenWith: (entry: VfsEntry, appKey: string) => void;
  onRename: (entry: VfsEntry) => void;
  onDelete: (entry: VfsEntry) => void;
  onContextMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
}

export const FileListView: React.FC<FileListViewProps> = ({
  entries,
  selectedEntries,
  onRowClick,
  onSelectionChange,
  onOpen,
  onOpenWith,
  onRename,
  onDelete,
  onContextMenu,
}) => {
  const { token } = theme.useToken();
  const { resolvedMode } = useTheme();
  const { t } = useI18n();
  const lightenColor = (hex: string, amount: number) => {
    const s = hex.replace('#', '');
    const n = s.length === 3 ? s.split('').map(c => c + c).join('') : s;
    const num = parseInt(n, 16);
    if (Number.isNaN(num) || n.length !== 6) return hex;
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    const mix = (c: number) => Math.round(c + (255 - c) * amount);
    const toHex = (v: number) => v.toString(16).padStart(2, '0');
    return `#${toHex(mix(r))}${toHex(mix(g))}${toHex(mix(b))}`;
  };

  const columns = [
    {
      title: t('Name'),
      dataIndex: 'name',
      key: 'name',
      render: (_: any, r: VfsEntry) => (
        <span style={{ cursor: 'pointer', userSelect: 'none' }} onDoubleClick={() => onOpen(r)}>
          {r.is_dir ? (
            <FolderFilled style={{ color: resolvedMode === 'dark' ? lightenColor(String(token.colorPrimary || '#111111'), 0.72) : token.colorPrimary, marginRight: 6 }} />
          ) : (
            getFileIcon(r.name, 16, resolvedMode)
          )}
          {r.name}
          {r.type === 'mount' && <Tooltip title={t('Mount Point')}><span style={{ marginLeft: 6, fontSize: 10, padding: '0 4px', border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 4 }}>MOUNT</span></Tooltip>}
        </span>
      )
    },
    { title: t('Size'), dataIndex: 'size', width: 100, render: (v: number, r: VfsEntry) => r.is_dir ? '-' : v },
    { title: t('Modified Time'), dataIndex: 'mtime', width: 160, render: (v: number) => v ? new Date(v * 1000).toLocaleString() : '-' },
    {
      title: t('Actions'),
      key: 'actions',
      width: 110,
      render: (_: any, r: VfsEntry) => {
        const apps = getAppsForEntry(r);
        const defaultApp = getDefaultAppForEntry(r);
        return (
          <Dropdown
            menu={{
              items: [
                (r.is_dir || apps.length > 0) ? { key: 'open', label: defaultApp ? `${t('Open')}(${defaultApp.name})` : t('Open'), icon: <FolderOpenOutlined />, onClick: () => onOpen(r) } : null,
                !r.is_dir && apps.length > 0 ? {
                  key: 'openWith',
                  label: t('Open With'),
                  icon: <AppstoreOutlined />,
                  children: apps.map(a => ({
                    key: 'openWith-' + a.key,
                    label: a.name + (a.key === defaultApp?.key ? ` (${t('Default')})` : ''),
                    onClick: () => onOpenWith(r, a.key)
                  }))
                } : null,
                { key: 'rename', label: t('Rename'), icon: <EditOutlined />, disabled: r.type === 'mount', onClick: () => onRename(r) },
                { key: 'delete', label: t('Delete'), icon: <DeleteOutlined />, danger: true, disabled: r.type === 'mount', onClick: () => onDelete(r) }
              ].filter(Boolean) as any[]
            }}
          >
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
        );
      }
    }
  ];

  return (
    <Table
      className="fx-file-table"
      rowKey={r => r.name}
      dataSource={entries}
      columns={columns as any}
      pagination={false}
      onRow={(r) => ({
        onClick: (e: any) => onRowClick(r, e),
        onDoubleClick: () => onOpen(r),
        onContextMenu: (e) => onContextMenu(e, r)
      })}
      rowClassName={(r) => selectedEntries.includes(r.name) ? 'row-selected' : ''}
      rowSelection={{
        selectedRowKeys: selectedEntries,
        onChange: (keys) => onSelectionChange(keys as string[]),
      }}
    />
  );
};
