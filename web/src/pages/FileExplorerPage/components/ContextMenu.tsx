import React from 'react';
import { Menu, theme } from 'antd';
import type { VfsEntry } from '../../../api/client';
import { getAppsForEntry, getDefaultAppForEntry } from '../../../apps/registry';
import { useI18n } from '../../../i18n';
import {
  FolderFilled, AppstoreOutlined, AppstoreAddOutlined, DownloadOutlined,
  EditOutlined, DeleteOutlined, InfoCircleOutlined, UploadOutlined, PlusOutlined,
  ShareAltOutlined, LinkOutlined, CopyOutlined, SwapOutlined
} from '@ant-design/icons';

interface ContextMenuProps {
  x: number;
  y: number;
  entry?: VfsEntry;
  entries: VfsEntry[];
  selectedEntries: string[];
  processorTypes: any[];
  onClose: () => void;
  onOpen: (entry: VfsEntry) => void;
  onOpenWith: (entry: VfsEntry, appKey: string) => void;
  onDownload: (entry: VfsEntry) => void;
  onRename: (entry: VfsEntry) => void;
  onDelete: (entries: VfsEntry[]) => void;
  onDetail: (entry: VfsEntry) => void;
  onProcess: (entry: VfsEntry, processorType: string) => void;
  onUpload: () => void;
  onCreateDir: () => void;
  onShare: (entries: VfsEntry[]) => void;
  onGetDirectLink: (entry: VfsEntry) => void;
  onMove: (entry: VfsEntry) => void;
  onCopy: (entry: VfsEntry) => void;
}

export const ContextMenu: React.FC<ContextMenuProps> = (props) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { x, y, entry, entries, selectedEntries, processorTypes, onClose, ...actions } = props;

  const getContextMenuItems = () => {
    if (!entry) { // Blank context menu
      return [
        { key: 'upload', label: t('Upload File'), icon: <UploadOutlined />, onClick: actions.onUpload },
        { key: 'mkdir', label: t('New Folder'), icon: <PlusOutlined />, onClick: actions.onCreateDir },
      ];
    }

    // Entry context menu
    const apps = getAppsForEntry(entry);
    const defaultApp = getDefaultAppForEntry(entry);
    const targetNames = selectedEntries.includes(entry.name) ? selectedEntries : [entry.name];
    const targetEntries = entries.filter(e => targetNames.includes(e.name));

    let processorSubMenu: any[] = [];
    if (!entry.is_dir && processorTypes.length > 0) {
      const ext = entry.name.split('.').pop()?.toLowerCase() || '';
      processorSubMenu = processorTypes
        .filter(pt => pt.supported_exts.includes(ext))
        .map(pt => ({
          key: 'processor-' + pt.type,
          label: pt.name,
          onClick: () => actions.onProcess(entry, pt.type),
        }));
    }

    return [
      (entry.is_dir || apps.length > 0) ? {
        key: 'open',
        label: defaultApp ? `${t('Open')} (${defaultApp.name})` : t('Open'),
        icon: <FolderFilled />,
        onClick: () => actions.onOpen(entry),
      } : null,
      !entry.is_dir && apps.length > 0 ? {
        key: 'openWith',
        label: t('Open With'),
        icon: <AppstoreOutlined />,
        children: apps.map(a => ({
          key: 'openWith-' + a.key,
          label: a.name + (a.key === defaultApp?.key ? ` (${t('Default')})` : ''),
          onClick: () => actions.onOpenWith(entry, a.key),
        })),
      } : null,
      !entry.is_dir && processorSubMenu.length > 0 ? {
        key: 'process',
        label: t('Processor'),
        icon: <AppstoreAddOutlined />,
        children: processorSubMenu,
      } : null,
      {
        key: 'share',
        label: t('Share'),
        icon: <ShareAltOutlined />,
        onClick: () => actions.onShare(targetEntries),
      },
      {
        key: 'directLink',
        label: t('Get Direct Link'),
        icon: <LinkOutlined />,
        disabled: targetEntries.length !== 1 || targetEntries[0].is_dir,
        onClick: () => actions.onGetDirectLink(targetEntries[0]),
      },
      {
        key: 'download',
        label: t('Download'),
        icon: <DownloadOutlined />,
        disabled: targetEntries.some(t => t.is_dir) || targetEntries.length > 1,
        onClick: () => actions.onDownload(targetEntries[0]),
      },
      {
        key: 'rename',
        label: t('Rename'),
        icon: <EditOutlined />,
        disabled: targetEntries.length !== 1 || targetEntries[0].type === 'mount',
        onClick: () => actions.onRename(targetEntries[0]),
      },
      {
        key: 'move',
        label: t('Move'),
        icon: <SwapOutlined />,
        disabled: targetEntries.length !== 1 || targetEntries[0].type === 'mount',
        onClick: () => actions.onMove(targetEntries[0]),
      },
      {
        key: 'copy',
        label: t('Copy'),
        icon: <CopyOutlined />,
        disabled: targetEntries.length !== 1 || targetEntries[0].type === 'mount',
        onClick: () => actions.onCopy(targetEntries[0]),
      },
      {
        key: 'delete',
        label: t('Delete'),
        icon: <DeleteOutlined />,
        danger: true,
        disabled: targetEntries.some(t => t.type === 'mount'),
        onClick: () => actions.onDelete(targetEntries),
      },
      {
        key: 'detail',
        label: t('Details'),
        icon: <InfoCircleOutlined />,
        onClick: () => actions.onDetail(entry),
      },
    ].filter(Boolean);
  };

  const items = getContextMenuItems()
    .filter(item => item !== null) // Ensure no null items
    .map(item => ({
      ...item,
      onClick: () => {
        if (item.onClick) item.onClick();
        onClose();
      }
    }));

  return (
    <div
      style={{ position: 'fixed', top: y, left: x, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.15)', borderRadius: token.borderRadius, background: token.colorBgElevated }}
      onContextMenu={(e) => e.preventDefault()}
      onClick={onClose} // Close on any click inside the menu area
    >
      <Menu
        items={items as any[]}
        selectable={false}
        style={{ width: 160, borderRadius: token.borderRadius, background: 'transparent' }}
      />
    </div>
  );
};
