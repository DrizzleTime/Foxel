import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Drawer, Menu, theme } from 'antd';
import type { MenuProps } from 'antd';
import type { VfsEntry } from '../../../api/client';
import { processorSupportsEntry, type ProcessorTypeMeta } from '../../../api/processors';
import { getAppsForEntry, getDefaultAppForEntry, usePluginApps } from '../../../apps/registry';
import { useI18n } from '../../../i18n';
import {
  FolderFilled, AppstoreOutlined, AppstoreAddOutlined, DownloadOutlined,
  EditOutlined, DeleteOutlined, InfoCircleOutlined, UploadOutlined, PlusOutlined,
  ShareAltOutlined, LinkOutlined, CopyOutlined, SwapOutlined, FileAddOutlined,
  PlayCircleOutlined, FileZipOutlined
} from '@ant-design/icons';

interface ContextMenuProps {
  x: number;
  y: number;
  mobile?: boolean;
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
  onProcess: (entries: VfsEntry[], processorType: string) => void;
  onUploadFile: () => void;
  onUploadDirectory: () => void;
  onCreateFile: () => void;
  onCreateDir: () => void;
  onShare: (entries: VfsEntry[]) => void;
  onCreateVideoRoom: (entry: VfsEntry) => void;
  onGetDirectLink: (entry: VfsEntry) => void;
  onMove: (entries: VfsEntry[]) => void;
  onCopy: (entries: VfsEntry[]) => void;
  canCompress: boolean;
  onCompress: (entries: VfsEntry[]) => void;
  canExtract: boolean;
  onExtract: (entry: VfsEntry) => void;
}

type MenuItem = Required<MenuProps>['items'][number];

const isVideoFile = (name: string) => /\.(mp4|webm|ogg|m4v|mov|mkv|avi|flv)$/i.test(name);

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
  usePluginApps();
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { x, y, mobile = false, entry, entries, selectedEntries, processorTypes, canCompress, canExtract, onClose, ...actions } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef(document.activeElement instanceof HTMLElement ? document.activeElement : null);
  const [position, setPosition] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    if (mobile) return;
    const container = containerRef.current;
    const target = container?.querySelector<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])')
      ?? container?.querySelector<HTMLElement>('[role="menu"]');
    target?.focus();
  }, [mobile]);

  useLayoutEffect(() => {
    setPosition({ left: x, top: y });
  }, [x, y]);

  useEffect(() => {
    if (mobile) return;

    const closeWhenOutside = (event: Event) => {
      if (event.target instanceof Node && !containerRef.current?.contains(event.target)) {
        onClose();
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        triggerRef.current?.focus();
      }
    };

    document.addEventListener('pointerdown', closeWhenOutside, true);
    document.addEventListener('focusin', closeWhenOutside, true);
    document.addEventListener('keydown', closeOnEscape, true);
    window.addEventListener('blur', onClose);
    return () => {
      document.removeEventListener('pointerdown', closeWhenOutside, true);
      document.removeEventListener('focusin', closeWhenOutside, true);
      document.removeEventListener('keydown', closeOnEscape, true);
      window.removeEventListener('blur', onClose);
    };
  }, [mobile, onClose]);

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
        { key: 'new-file', label: t('New File'), icon: <FileAddOutlined />, onClick: actions.onCreateFile },
        { key: 'mkdir', label: t('New Folder'), icon: <PlusOutlined />, onClick: actions.onCreateDir },
      ];
    }

    // Entry context menu
    const apps = getAppsForEntry(entry);
    const defaultApp = getDefaultAppForEntry(entry);
    const targetNames = selectedEntries.includes(entry.name) ? selectedEntries : [entry.name];
    const targetEntries = entries.filter(e => targetNames.includes(e.name));

    const processorSubMenu: ActionMenuItem[] = processorTypes
      .filter(pt => targetEntries.length > 0 && targetEntries.every(target => processorSupportsEntry(pt, target)))
      .map(pt => ({
        key: 'processor-' + pt.type,
        label: pt.name,
        onClick: () => actions.onProcess(targetEntries, pt.type),
      }));

    const menuItems: (ActionMenuItem | null)[] = [
      (entry.is_dir || apps.length > 0) ? {
        key: 'open',
        label: t('Open'),
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
      processorSubMenu.length > 0 ? {
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
        key: 'videoRoom',
        label: t('Create Video Room'),
        icon: <PlayCircleOutlined />,
        disabled: targetEntries.length !== 1 || targetEntries[0].is_dir || !isVideoFile(targetEntries[0].name),
        onClick: () => actions.onCreateVideoRoom(targetEntries[0]),
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
      canCompress ? {
        key: 'compress',
        label: t('Compress to ZIP'),
        icon: <FileZipOutlined />,
        disabled: targetEntries.length === 0 || targetEntries.some(target => target.type === 'mount'),
        onClick: () => actions.onCompress(targetEntries),
      } : null,
      canExtract && !entry.is_dir && /\.zip$/i.test(entry.name) ? {
        key: 'extract',
        label: t('Extract ZIP'),
        icon: <FileZipOutlined />,
        disabled: targetEntries.length !== 1,
        onClick: () => actions.onExtract(entry),
      } : null,
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

    return menuItems.filter((item): item is ActionMenuItem => item !== null && !item.disabled);
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

  if (mobile) {
    return (
      <Drawer
        open
        placement="bottom"
        onClose={onClose}
        title={entry ? t('Actions') : t('Quick Actions')}
        size="auto"
        styles={{ body: { padding: 8 } }}
      >
        <div onClick={(e) => e.stopPropagation()}>
          <Menu
            aria-label={entry ? t('More actions for {name}', { name: entry.name }) : t('Quick Actions')}
            items={items}
            mode="inline"
            selectable={false}
            onClick={({ key }) => {
              const handler = handlerMap.get(String(key));
              if (!handler) return;
              handler();
              onClose();
            }}
            style={{ borderRadius: token.borderRadius, background: 'transparent', border: 'none' }}
          />
        </div>
      </Drawer>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{ position: 'fixed', top: position.top, left: position.left, zIndex: 9999, boxShadow: '0 4px 16px rgba(0,0,0,.15)', borderRadius: token.borderRadius, background: token.colorBgElevated }}
      onContextMenu={(e) => e.preventDefault()}
      onClick={(e) => e.stopPropagation()}
    >
      <Menu
        aria-label={entry ? t('More actions for {name}', { name: entry.name }) : t('Quick Actions')}
        items={items}
        selectable={false}
        getPopupContainer={() => containerRef.current ?? document.body}
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
