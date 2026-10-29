import React from 'react';
import { Table, Dropdown, Button, Checkbox, Tooltip, theme } from 'antd';
import { FolderFilled, MoreOutlined, EditOutlined, DeleteOutlined, AppstoreOutlined, FolderOpenOutlined, RightOutlined } from '@ant-design/icons';
import type { VfsEntry } from '../../../api/client';
import { getFileIcon } from './FileIcons';
import { getAppsForEntry, getDefaultAppForEntry, usePluginApps } from '../../../apps/registry';
import { useTheme } from '../../../contexts/ThemeContext';
import { useI18n } from '../../../i18n';
import FileThumbnail from '../../../components/FileThumbnail';

interface FileListViewProps {
  entries: VfsEntry[];
  mobile?: boolean;
  thumbs?: Record<string, string>;
  selectedEntries: string[];
  onRowClick: (entry: VfsEntry, e: React.MouseEvent) => void;
  onSelectionChange: (selectedKeys: string[]) => void;
  onOpen: (entry: VfsEntry) => void;
  onOpenWith: (entry: VfsEntry, appKey: string) => void;
  onRename: (entry: VfsEntry) => void;
  onDelete: (entry: VfsEntry) => void;
  onContextMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
  onOpenMenu?: (entry: VfsEntry, anchor: HTMLElement) => void;
  batchMode?: boolean;
  batchSelectedNames?: Set<string>;
  onBatchToggle?: (entry: VfsEntry) => void;
}

const fileTypeGroups: Array<{ key: string; exts: string[] }> = [
  { key: 'Image', exts: ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff'] },
  { key: 'Video', exts: ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'm4v', '3gp'] },
  { key: 'Audio', exts: ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a'] },
  { key: 'PDF', exts: ['pdf'] },
  { key: 'Word', exts: ['doc', 'docx'] },
  { key: 'Spreadsheet', exts: ['xls', 'xlsx', 'csv'] },
  { key: 'Presentation', exts: ['ppt', 'pptx'] },
  { key: 'Archive', exts: ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'] },
  { key: 'Code', exts: ['js', 'jsx', 'ts', 'tsx', 'vue', 'html', 'htm', 'css', 'scss', 'sass', 'less', 'json', 'xml', 'yaml', 'yml', 'py', 'java', 'cpp', 'cc', 'cxx', 'c', 'h', 'hpp', 'hxx', 'php', 'rb', 'go', 'rs', 'rust', 'swift', 'kt', 'scala', 'clj', 'cljs', 'cs', 'vb', 'fs', 'pl', 'pm', 'r', 'lua', 'dart', 'elm'] },
  { key: 'Markdown', exts: ['md', 'markdown'] },
  { key: 'Text', exts: ['txt', 'log', 'ini', 'cfg', 'conf', 'sh', 'bash', 'zsh', 'fish', 'ps1', 'bat', 'cmd', 'dockerfile', 'makefile', 'gradle', 'cmake', 'gitignore', 'gitattributes', 'editorconfig', 'prettierrc'] },
  { key: 'Font', exts: ['ttf', 'otf', 'woff', 'woff2', 'eot'] },
  { key: 'Database', exts: ['db', 'sqlite', 'sql'] },
  { key: 'Config', exts: ['env', 'config', 'properties', 'toml'] },
];

const formatFileSize = (size: number) => {
  if (!Number.isFinite(size) || size < 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  if (unitIndex === 0) return `${value} ${units[unitIndex]}`;
  return `${value.toFixed(2)} ${units[unitIndex]}`;
};

const getFileTypeLabel = (entry: VfsEntry, t: (key: string) => string) => {
  if (entry.type === 'mount') return t('Mount Point');
  if (entry.is_dir) return t('Folder');

  const ext = entry.name.split('.').pop()?.toLowerCase() || '';
  const group = fileTypeGroups.find(item => item.exts.includes(ext));
  return t(group?.key || 'File');
};

export const FileListView: React.FC<FileListViewProps> = ({
  entries,
  mobile = false,
  thumbs = {},
  selectedEntries,
  onRowClick,
  onSelectionChange,
  onOpen,
  onOpenWith,
  onRename,
  onDelete,
  onContextMenu,
  onOpenMenu,
  batchMode = false,
  batchSelectedNames,
  onBatchToggle,
}) => {
  usePluginApps();
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

  if (mobile) {
    return (
      <div style={{ padding: '0 12px' }}>
        {entries.map((entry, index) => {
          const checked = !!batchSelectedNames?.has(entry.name);
          const selectable = entry.type !== 'mount';
          const activate = () => {
            if (batchMode) {
              onBatchToggle?.(entry);
            } else {
              onOpen(entry);
            }
          };
          const metadata = [
            entry.is_dir ? getFileTypeLabel(entry, t) : formatFileSize(entry.size),
            entry.mtime ? new Date(entry.mtime * 1000).toLocaleString() : '',
          ].filter(Boolean).join(' · ');

          return (
            <div
              key={entry.name}
              onClick={activate}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, minWidth: 0,
                padding: '12px 0', borderBottom: `1px solid ${token.colorBorderSecondary}`,
                background: batchMode && checked ? token.controlItemBgActive : undefined,
                cursor: 'pointer', userSelect: 'none',
              }}
            >
              {batchMode && (
                <Checkbox
                  checked={checked}
                  disabled={!selectable}
                  aria-label={t(checked ? 'Deselect' : 'Select')}
                  onClick={event => event.stopPropagation()}
                  onChange={() => onBatchToggle?.(entry)}
                />
              )}
              <div
                data-file-item
                role="button"
                tabIndex={0}
                aria-label={entry.name}
                aria-pressed={batchMode && selectable ? checked : undefined}
                onKeyDown={event => {
                  if (event.target !== event.currentTarget) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    activate();
                  }
                }}
                style={{ display: 'flex', alignItems: 'center', gap: 12, flex: 1, minWidth: 0 }}
              >
                <div style={{ width: 40, height: 40, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative' }}>
                  {entry.is_dir ? (
                    <FolderFilled style={{ fontSize: 32, color: resolvedMode === 'dark' ? lightenColor(String(token.colorPrimary || '#111111'), 0.72) : token.colorPrimary }} />
                  ) : thumbs[entry.name] ? (
                    <FileThumbnail src={thumbs[entry.name]} alt="" eager={index < 12} fallback={getFileIcon(entry.name, 32, resolvedMode)} style={{ width: '100%', height: '100%', objectFit: 'contain', borderRadius: token.borderRadiusSM }} />
                  ) : getFileIcon(entry.name, 32, resolvedMode)}
                  {entry.type === 'mount' && (
                    <span title={t('Mount Point')} style={{ position: 'absolute', right: 0, bottom: 0, fontSize: 10, padding: '0 3px', background: token.colorBgContainer, border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 4 }}>M</span>
                  )}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="ellipsis" title={entry.name} style={{ color: token.colorText }}>{entry.name}</div>
                  <div className="ellipsis" style={{ marginTop: 4, fontSize: 12, color: token.colorTextSecondary }}>{metadata}</div>
                </div>
              </div>
              {batchMode ? entry.is_dir && (
                <Button
                  className="fx-file-more-button"
                  type="text"
                  icon={<RightOutlined />}
                  aria-label={t('Open')}
                  onClick={event => {
                    event.stopPropagation();
                    onOpen(entry);
                  }}
                  style={{ flexShrink: 0 }}
                />
              ) : onOpenMenu && (
                <Button
                  className="fx-file-more-button"
                  type="text"
                  icon={<MoreOutlined />}
                  aria-label={t('More actions for {name}', { name: entry.name })}
                  onClick={event => {
                    event.stopPropagation();
                    onOpenMenu(entry, event.currentTarget);
                  }}
                  style={{ flexShrink: 0 }}
                />
              )}
            </div>
          );
        })}
      </div>
    );
  }

  const columns = [
    {
      title: t('Name'),
      dataIndex: 'name',
      key: 'name',
      render: (_: any, r: VfsEntry) => (
        <button
          type="button"
          className="fx-text-button"
          data-file-item
          onClick={event => {
            if (event.detail === 0) {
              event.stopPropagation();
              onOpen(r);
            }
          }}
          onDoubleClick={event => { event.stopPropagation(); onOpen(r); }}
          style={{ userSelect: 'none' }}
        >
          {r.is_dir ? (
            <FolderFilled style={{ color: resolvedMode === 'dark' ? lightenColor(String(token.colorPrimary || '#111111'), 0.72) : token.colorPrimary, marginRight: 6 }} />
          ) : (
            getFileIcon(r.name, 16, resolvedMode)
          )}
          {r.name}
          {r.type === 'mount' && <Tooltip title={t('Mount Point')}><span style={{ marginLeft: 6, fontSize: 10, padding: '0 4px', border: `1px solid ${token.colorBorderSecondary}`, borderRadius: 4 }}>MOUNT</span></Tooltip>}
        </button>
      )
    },
    { title: t('Type'), key: 'fileType', width: 110, render: (_: any, r: VfsEntry) => getFileTypeLabel(r, t) },
    { title: t('Size'), dataIndex: 'size', width: 120, render: (v: number, r: VfsEntry) => r.is_dir ? '-' : formatFileSize(v) },
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
            <Button size="small" icon={<MoreOutlined />} aria-label={t('More actions for {name}', { name: r.name })} />
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
      scroll={{ x: 'max-content' }}
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
