import { useCallback } from 'react';
import { message, Modal } from 'antd';
import { useI18n } from '../../../i18n';
import { vfsApi, type VfsEntry } from '../../../api/client';

interface FileActionsParams {
  path: string;
  refresh: () => void;
  clearSelection: () => void;
  onShare: (entries: VfsEntry[]) => void;
  onGetDirectLink: (entry: VfsEntry) => void;
}

export function useFileActions({ path, refresh, clearSelection, onShare, onGetDirectLink }: FileActionsParams) {
  const { t } = useI18n();
  const normalizeFullPath = useCallback((name: string) => {
    const base = path === '/' ? '' : path;
    return `${base}/${name}`.replace(/\/{2,}/g, '/');
  }, [path]);

  const normalizeDestination = useCallback((dest: string) => {
    const trimmed = dest.trim();
    if (!trimmed) return '';
    const normalized = trimmed.startsWith('/') ? trimmed : `/${trimmed}`;
    return normalized.replace(/\/{2,}/g, '/');
  }, []);
  const doCreateDir = useCallback(async (name: string) => {
    if (!name.trim()) {
      message.warning(t('Please input name'));
      return;
    }
    try {
      await vfsApi.mkdir((path === '/' ? '' : path) + '/' + name.trim());
      refresh();
    } catch (e: any) {
      message.error(e.message);
    }
  }, [path, refresh]);

  const doDelete = useCallback(async (entries: VfsEntry[]) => {
    Modal.confirm({
      title: t('Confirm delete {name}?', { name: entries.length > 1 ? `${entries.length} ${t('items')}` : entries[0].name }),
      content: entries.length > 1 ? <div style={{ maxHeight: 180, overflow: 'auto' }}>{entries.map(it => <div key={it.name}>{it.name}{it.type === 'mount' && ` (${t('Mount Point')})`}</div>)}</div> : null,
      onOk: async () => {
        try {
          await Promise.all(entries.map(it => vfsApi.deletePath((path === '/' ? '' : path) + '/' + it.name)));
          clearSelection();
          refresh();
        } catch (e: any) {
          message.error(e.message);
        }
      }
    });
  }, [path, refresh, clearSelection]);

  const doRename = useCallback(async (entry: VfsEntry, newName: string) => {
    if (!newName.trim() || newName.trim() === entry.name) {
      return;
    }
    try {
      await vfsApi.rename(
        (path === '/' ? '' : path) + '/' + entry.name,
        (path === '/' ? '' : path) + '/' + newName.trim()
      );
      refresh();
    } catch (e: any) {
      message.error(e.message);
    }
  }, [path, refresh]);

  const buildEntryDestination = useCallback((base: string, name: string) => {
    const normalizedBase = base.replace(/\/+$/, '') || '/';
    const prefix = normalizedBase === '/' ? '' : normalizedBase;
    const combined = `${prefix}/${name}`.replace(/\/{2,}/g, '/');
    return combined.startsWith('/') ? combined : `/${combined}`;
  }, []);

  const doMove = useCallback(async (entriesToMove: VfsEntry[], destination: string, overwrite: boolean = false) => {
    if (!entriesToMove || entriesToMove.length === 0) return;
    const normalized = normalizeDestination(destination);
    if (!normalized) {
      message.warning(t('Please input destination path'));
      return;
    }

    const multiple = entriesToMove.length > 1;
    const targetDir = multiple ? (normalized === '/' ? '/' : normalized.replace(/\/+$/, '') || '/') : normalized;
    let completedCount = 0;
    let queuedCount = 0;

    for (const entry of entriesToMove) {
      const src = normalizeFullPath(entry.name);
      const dst = multiple ? buildEntryDestination(targetDir, entry.name) : normalized;
      try {
        const result = await vfsApi.move(src, dst, { overwrite });
        if (result?.queued) {
          queuedCount += 1;
        } else {
          completedCount += 1;
        }
      } catch (e: any) {
        message.error(e.message);
        throw e;
      }
    }

    if (completedCount > 0) {
      message.success(t('Move completed'));
    }
    if (queuedCount > 0) {
      message.info(t('Move task queued'));
    }

    clearSelection();
    refresh();
  }, [normalizeDestination, normalizeFullPath, t, buildEntryDestination, clearSelection, refresh]);

  const doCopy = useCallback(async (entriesToCopy: VfsEntry[], destination: string, overwrite: boolean = false) => {
    if (!entriesToCopy || entriesToCopy.length === 0) return;
    const normalized = normalizeDestination(destination);
    if (!normalized) {
      message.warning(t('Please input destination path'));
      return;
    }

    const multiple = entriesToCopy.length > 1;
    const targetDir = multiple ? (normalized === '/' ? '/' : normalized.replace(/\/+$/, '') || '/') : normalized;
    let completedCount = 0;
    let queuedCount = 0;

    for (const entry of entriesToCopy) {
      const src = normalizeFullPath(entry.name);
      const dst = multiple ? buildEntryDestination(targetDir, entry.name) : normalized;
      try {
        const result = await vfsApi.copy(src, dst, { overwrite });
        if (result?.queued) {
          queuedCount += 1;
        } else {
          completedCount += 1;
        }
      } catch (e: any) {
        message.error(e.message);
        throw e;
      }
    }

    if (completedCount > 0) {
      message.success(t('Copy completed'));
    }
    if (queuedCount > 0) {
      message.info(t('Copy task queued'));
    }

    refresh();
  }, [normalizeDestination, normalizeFullPath, t, buildEntryDestination, refresh]);

  const doDownload = useCallback(async (entry: VfsEntry) => {
    if (entry.is_dir) {
      message.warning(t('Downloading folders is not supported'));
      return;
    }
    try {
      const buf = await vfsApi.readFile((path === '/' ? '' : path) + '/' + entry.name);
      const blob = new Blob([buf]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = entry.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      message.error(e.message || t('Download failed'));
    }
  }, [path]);

  const doShare = useCallback((entries: VfsEntry[]) => {
    if (entries.length === 0) {
      message.warning(t('Please select files or folders to share'));
      return;
    }
    onShare(entries);
  }, [onShare]);

  const doGetDirectLink = useCallback((entry: VfsEntry) => {
    if (entry.is_dir) {
      message.warning(t('Direct links for folders are not supported'));
      return;
    }
    onGetDirectLink(entry);
  }, [onGetDirectLink]);

  return {
    doCreateDir,
    doDelete,
    doRename,
    doDownload,
    doShare,
    doGetDirectLink,
    doMove,
    doCopy,
  };
}
