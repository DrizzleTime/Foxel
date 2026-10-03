import { useCallback, useEffect, useRef } from 'react';
import { Button, message, Modal, Progress, Tooltip } from 'antd';
import { CloseOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import { vfsApi, type VfsEntry } from '../../../api/client';
import { API_BASE_URL } from '../../../api/client';
import { downloadRanges, encodeFilePath, MAX_BLOB_DOWNLOAD_SIZE, saveDownloadUrl,
  selectDownloadTarget, TRANSFER_CHUNK_SIZE } from '../../../api/transfers';
import type { DownloadTarget } from '../../../api/transfers';

interface FileActionsParams {
  path: string;
  refresh: () => void;
  clearSelection: () => void;
  onShare: (entries: VfsEntry[]) => void;
  onGetDirectLink: (entry: VfsEntry) => void;
}

export function useFileActions({ path, refresh, clearSelection, onShare, onGetDirectLink }: FileActionsParams) {
  const { t } = useI18n();
  const downloadsRef = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const downloads = downloadsRef.current;
    return () => { for (const controller of downloads.values()) controller.abort(); };
  }, []);
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
  }, [path, refresh, t]);

  const doCreateFile = useCallback(async (name: string) => {
    if (!name.trim()) {
      message.warning(t('Please input name'));
      return;
    }
    try {
      const fullPath = (path === '/' ? '' : path) + '/' + name.trim();
      await vfsApi.uploadFile(fullPath, new Blob([]));
      refresh();
    } catch (e: any) {
      message.error(e.message);
    }
  }, [path, refresh, t]);

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
  }, [path, refresh, clearSelection, t]);

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
    const fullPath = normalizeFullPath(entry.name);
    if (downloadsRef.current.has(fullPath)) return;
    const controller = new AbortController();
    downloadsRef.current.set(fullPath, controller);
    const key = `download:${fullPath}`;
    let target: DownloadTarget | undefined;
    let lastUpdate = 0;
    const report = (loaded: number, total: number) => {
      if (Date.now() - lastUpdate < 200 && loaded < total) return;
      lastUpdate = Date.now();
      message.open({ key, duration: 0, content: <div style={{ width: 280, maxWidth: '70vw', textAlign: 'left' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{entry.name}</span>
          <Tooltip title={t('Cancel')}><Button type="text" size="small" icon={<CloseOutlined />}
            aria-label={t('Cancel')} onClick={() => controller.abort()} /></Tooltip>
        </div>
        <Progress percent={total ? Math.min(99, Math.round(loaded / total * 100)) : 0} size="small" />
      </div> });
    };
    try {
      // The picker must be called while the click still has user activation.
      const handle = entry.size > TRANSFER_CHUNK_SIZE ? await selectDownloadTarget(entry.name) : undefined;
      controller.signal.throwIfAborted();
      const optimized = entry.size > TRANSFER_CHUNK_SIZE
        && (handle !== undefined || entry.size <= MAX_BLOB_DOWNLOAD_SIZE);
      if (optimized) {
        target = await handle?.createWritable();
        report(0, entry.size);
        const blob = await downloadRanges(`${API_BASE_URL}/fs/download/${encodeFilePath(fullPath)}`,
          entry.size, report, controller.signal, target);
        if (blob !== null) {
          if (target) {
            await target.close();
            target = undefined;
          } else {
            const objectUrl = URL.createObjectURL(blob);
            saveDownloadUrl(objectUrl, entry.name);
            setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
          }
          message.success({ key, content: t('Download completed') });
          return;
        }
        await target?.abort();
        target = undefined;
      }
      const link = await vfsApi.getTempLinkToken(fullPath);
      controller.signal.throwIfAborted();
      saveDownloadUrl(`${API_BASE_URL}/fs/download-public/${encodeURIComponent(link.token)}/${encodeURIComponent(entry.name)}`, entry.name);
      message.destroy(key);
    } catch (error) {
      await target?.abort().catch(() => void 0);
      if ((error as Error).name === 'AbortError' || controller.signal.aborted) message.destroy(key);
      else message.error({ key, content: error instanceof Error ? error.message : t('Download failed') });
    } finally {
      downloadsRef.current.delete(fullPath);
    }
  }, [normalizeFullPath, t]);

  const doShare = useCallback((entries: VfsEntry[]) => {
    if (entries.length === 0) {
      message.warning(t('Please select files or folders to share'));
      return;
    }
    onShare(entries);
  }, [onShare, t]);

  const doGetDirectLink = useCallback((entry: VfsEntry) => {
    if (entry.is_dir) {
      message.warning(t('Direct links for folders are not supported'));
      return;
    }
    onGetDirectLink(entry);
  }, [onGetDirectLink, t]);

  return {
    doCreateDir,
    doCreateFile,
    doDelete,
    doRename,
    doDownload,
    doShare,
    doGetDirectLink,
    doMove,
    doCopy,
  };
}
