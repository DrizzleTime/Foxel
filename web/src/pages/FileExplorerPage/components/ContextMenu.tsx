import React, { useLayoutEffect, useRef, useState } from 'react';
import { Menu, theme } from 'antd';
import type { MenuProps } from 'antd';
import type { VfsEntry } from '../../../api/client';
import type { ProcessorTypeMeta } from '../../../api/processors';
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
  processorTypes: ProcessorTypeMeta[];
  onClose: () => void;
  onOpen: (entry: VfsEntry) => void;
  onOpenWith: (entry: VfsEntry, appKey: string) => void;
  onDownload: (entry: VfsEntry) => void;
  onRename: (entry: VfsEntry) => void;
  onDelete: (entries: VfsEntry[]) => void;
  onDetail: (entry: VfsEntry) => void;
  onProcess: (entry: VfsEntry, processorType: string) => void;
  onUploadFile: () => void;
  onUploadDirectory: () => void;
  onCreateDir: () => void;
  onShare: (entries: VfsEntry[]) => void;
  onGetDirectLink: (entry: VfsEntry) => void;
  onMove: (entries: VfsEntry[]) => void;
  onCopy: (entries: VfsEntry[]) => void;
}

type MenuItem = Required<MenuProps>['items'][number];

interface ActionMenuItem {
  key: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  disabled?: boolean;
  danger?: boolean;
  onClick?: () => void;
  children?: ActionMenuItem[];
}

export const ContextMenu: React.FC<ContextMenuProps> = (props) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { x, y, entry, entries, selectedEntries, processorTypes, onClose, ...actions } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    setPosition({ left: x, top: y });
  }, [x, y]);

  const getContextMenuItems = (): ActionMenuItem[] => {
    if (!entry) { // Blank context menu
      return [
        {
          key: 'upload',
          label: t('Upload'),
          icon: <UploadOutlined />,
          children: [
            { key: 'upload-file', label: t('Upload Files'), onClick: actions.onUploadFile },
            { key: 'upload-folder', label: t('Upload Folder'), onClick: actions.onUploadDirectory },
          ],
        },
        { key: 'mkdir', label: t('New Folder'), icon: <PlusOutlined />, onClick: actions.onCreateDir },
      ];
    }

    // Entry context menu
    const apps = getAppsForEntry(entry);
    const defaultApp = getDefaultAppForEntry(entry);
    const targetNames = selectedEntries.includes(entry.name) ? selectedEntries : [entry.name];
    const targetEntries = entries.filter(e => targetNames.includes(e.name));

    let processorSubMenu: ActionMenuItem[] = [];
    if (!entry.is_dir && processorTypes.length > 0) {
      const ext = entry.name.split('.').pop()?.toLowerCase() || '';
      processorSubMenu = processorTypes
        .filter(pt => {
          const exts = pt.supported_exts;
          if (!Array.isArray(exts) || exts.length === 0) return true;
          return exts.includes(ext);
        })
        .map(pt => ({
          key: 'processor-' + pt.type,
          label: pt.name,
          onClick: () => actions.onProcess(entry, pt.type),
        }));
    }

    const menuItems: (ActionMenuItem | null)[] = [
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
        disabled: targetEntries.length === 0 || targetEntries.some(t => t.type === 'mount'),
        onClick: () => actions.onMove(targetEntries),
      },
      {
        key: 'copy',
        label: t('Copy'),
        icon: <CopyOutlined />,
        disabled: targetEntries.length === 0 || targetEntries.some(t => t.type === 'mount'),
        onClick: () => actions.onCopy(targetEntries),
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
    ];

    return menuItems.filter((item): item is ActionMenuItem => item !== null);
  };

  const actionItems = getContextMenuItems();

  const handlerMap = new Map<string, () => void>();

  const mapItems = (source: ActionMenuItem[]): MenuItem[] =>
    source.map<MenuItem>((item) => {
      if (item.onClick) handlerMap.set(item.key, item.onClick);
      const mappedChildren = item.children && item.children.length > 0 ? mapItems(item.children) : undefined;

      const transformed = {
        key: item.key,
        label: item.label,
        icon: item.icon,
        disabled: item.disabled,
        danger: item.danger,
        ...(mappedChildren ? { children: mappedChildren } : {}),
      } as MenuItem;
      return transformed;
    });

  const items = mapItems(actionItems);

  useLayoutEffect(() => {
    if (typeof window === 'undefined') return;
    const node = containerRef.current;
    if (!node) return;

    const margin = 8;
    const { offsetWidth, offsetHeight } = node;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    let nextLeft = position.left;
    let nextTop = position.top;

    if (nextLeft + offsetWidth + margin > viewportWidth) {
      nextLeft = Math.max(margin, viewportWidth - offsetWidth - margin);
    }
    if (nextTop + offsetHeight + margin > viewportHeight) {
      nextTop = Math.max(margin, viewportHeight - offsetHeight - margin);
    }
    if (nextLeft < margin) {
      nextLeft = margin;
    }
    if (nextTop < margin) {
      nextTop = margin;
    }

    if (nextLeft !== position.left || nextTop !== position.top) {
      setPosition({ left: nextLeft, top: nextTop });
    }
  }, [position.left, position.top, items.length]);

  return (
    <div
      ref={containerRef}
      style={{ position: 'fixed', top: position.top, left: position.left, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.15)', borderRadius: token.borderRadius, background: token.colorBgElevated }}
      onContextMenu={(e) => e.preventDefault()}
      onClick={onClose} // Close on any click inside the menu area
    >
      <Menu
        items={items}
        selectable={false}
        onClick={({ key }) => {
          const handler = handlerMap.get(String(key));
          if (handler) handler();
          onClose();
        }}
        style={{ width: 160, borderRadius: token.borderRadius, background: 'transparent' }}
      />
    </div>
  );
};
