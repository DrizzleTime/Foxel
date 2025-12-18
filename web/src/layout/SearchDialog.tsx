import { Modal, Input, List, Divider, Spin, Space, Tag, Typography, Empty, Flex, Segmented, Pagination, message } from 'antd';
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import React, { useRef, useState, useEffect, useCallback } from 'react';
import { vfsApi, type SearchResultItem } from '../api/vfs';
import { type VfsEntry } from '../api/client';
import { processorsApi, type ProcessorTypeMeta } from '../api/processors';
import { useI18n } from '../i18n';
import { useNavigate } from 'react-router';
import { useAppWindows } from '../contexts/AppWindowsContext';
import { ContextMenu } from '../pages/FileExplorerPage/components/ContextMenu';
import { RenameModal } from '../pages/FileExplorerPage/components/Modals/RenameModal';
import { MoveCopyModal } from '../pages/FileExplorerPage/components/Modals/MoveCopyModal';
import { ShareModal } from '../pages/FileExplorerPage/components/Modals/ShareModal';
import { DirectLinkModal } from '../pages/FileExplorerPage/components/Modals/DirectLinkModal';
import { FileDetailModal } from '../pages/FileExplorerPage/components/FileDetailModal';
import { ProcessorModal } from '../pages/FileExplorerPage/components/Modals/ProcessorModal';
import { useFileActions } from '../pages/FileExplorerPage/hooks/useFileActions.tsx';
import { useProcessor } from '../pages/FileExplorerPage/hooks/useProcessor';

interface SearchDialogProps {
  open: boolean;
  onClose: () => void;
}

type SearchMode = 'vector' | 'filename';
const PAGE_SIZE = 10;

const SearchDialog: React.FC<SearchDialogProps> = ({ open, onClose }) => {
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [searched, setSearched] = useState(false);
  const [searchMode, setSearchMode] = useState<SearchMode>('vector');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const requestIdRef = useRef(0);
  const { t } = useI18n();
  const navigate = useNavigate();
  const { openFileWithDefaultApp, confirmOpenWithApp } = useAppWindows();
  const statCacheRef = useRef<Map<string, VfsEntry>>(new Map());

  const [contextMenuState, setContextMenuState] = useState<{ entry: VfsEntry; x: number; y: number; path: string } | null>(null);
  const [menuEntries, setMenuEntries] = useState<VfsEntry[]>([]);
  const [selectedEntryNames, setSelectedEntryNames] = useState<string[]>([]);
  const [currentPath, setCurrentPath] = useState<string>('/');
  const [processorTypes, setProcessorTypes] = useState<ProcessorTypeMeta[]>([]);
  const [renaming, setRenaming] = useState<VfsEntry | null>(null);
  const [sharingEntries, setSharingEntries] = useState<VfsEntry[]>([]);
  const [directLinkEntry, setDirectLinkEntry] = useState<VfsEntry | null>(null);
  const [detailEntry, setDetailEntry] = useState<VfsEntry | null>(null);
  const [detailData, setDetailData] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [movingEntries, setMovingEntries] = useState<VfsEntry[]>([]);
  const [copyingEntries, setCopyingEntries] = useState<VfsEntry[]>([]);

  const closeContextMenu = useCallback(() => {
    setContextMenuState(null);
    setMenuEntries([]);
    setSelectedEntryNames([]);
  }, []);

  const noop = useCallback(() => {}, []);

  const handleShare = useCallback((entries: VfsEntry[]) => {
    setSharingEntries(entries);
  }, []);

  const handleDirectLink = useCallback((entry: VfsEntry) => {
    setDirectLinkEntry(entry);
  }, []);

  const { doDelete, doDownload, doRename, doShare, doGetDirectLink, doMove, doCopy } = useFileActions({
    path: currentPath,
    refresh: noop,
    clearSelection: noop,
    onShare: handleShare,
    onGetDirectLink: handleDirectLink,
  });

  const processorHook = useProcessor({ path: currentPath, processorTypes, refresh: noop });

  useEffect(() => {
    if (!open) {
      statCacheRef.current.clear();
      setProcessorTypes([]);
      closeContextMenu();
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const list = await processorsApi.list();
        if (!cancelled) {
          setProcessorTypes(list);
        }
      } catch (e) {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : t('Load failed');
        message.error(msg);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, closeContextMenu, t]);

  const handleClose = useCallback(() => {
    setSearch('');
    setResults([]);
    setSearched(false);
    setSearchMode('vector');
    setPage(1);
    setHasMore(false);
    requestIdRef.current = 0;
    setLoading(false);
    closeContextMenu();
    setProcessorTypes([]);
    setRenaming(null);
    setSharingEntries([]);
    setDirectLinkEntry(null);
    setDetailEntry(null);
    setDetailData(null);
    setDetailLoading(false);
    setMovingEntries([]);
    setCopyingEntries([]);
    setCurrentPath('/');
    statCacheRef.current.clear();
    onClose();
  }, [closeContextMenu, onClose]);

  const renderSourceLabel = (value?: string) => {
    switch ((value || '').toLowerCase()) {
      case 'vector':
        return t('Vector Search');
      case 'filename':
        return t('Name Search');
      case 'text':
        return t('Text Chunk');
      case 'image':
        return t('Image Description');
      default:
        return t('Vector Search');
    }
  };

  const sourceColor = (value?: string) => {
    switch ((value || '').toLowerCase()) {
      case 'vector':
        return 'blue';
      case 'filename':
        return 'green';
      case 'image':
        return 'volcano';
      case 'text':
        return 'geekblue';
      default:
        return 'purple';
    }
  };

  const buildFullPath = useCallback((entryName: string, basePath?: string) => {
    const dir = basePath ?? currentPath;
    const prefix = dir === '/' ? '' : dir;
    const combined = `${prefix}/${entryName}`.replace(/\/{2,}/g, '/');
    if (!combined) return '/';
    return combined.startsWith('/') ? combined : `/${combined}`;
  }, [currentPath]);

  const buildDefaultDestination = useCallback((targetEntries: VfsEntry[]) => {
    if (!targetEntries || targetEntries.length === 0) return '';
    if (targetEntries.length > 1) {
      return currentPath || '/';
    }
    const entry = targetEntries[0];
    const base = currentPath === '/' ? '' : currentPath;
    const segments = [base, entry.name].filter(Boolean);
    const joined = segments.join('/');
    if (!joined) return '/';
    return joined.startsWith('/') ? joined : `/${joined}`;
  }, [currentPath]);

  const openDetail = useCallback(async (entry: VfsEntry) => {
    setDetailEntry(entry);
    setDetailLoading(true);
    try {
      const stat = await vfsApi.stat(buildFullPath(entry.name));
      setDetailData(stat);
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('Load failed');
      setDetailData({ error: msg });
      message.error(msg);
    } finally {
      setDetailLoading(false);
    }
  }, [buildFullPath, t]);

  const handleOpenEntry = useCallback((entry: VfsEntry) => {
    const basePath = contextMenuState?.path ?? currentPath;
    if (entry.is_dir) {
      const next = buildFullPath(entry.name, basePath);
      navigate(`/files${next === '/' ? '' : next}`, { state: { highlight: { name: entry.name } } });
      closeContextMenu();
      handleClose();
      return;
    }
    openFileWithDefaultApp(entry, basePath);
    closeContextMenu();
    handleClose();
  }, [buildFullPath, navigate, closeContextMenu, handleClose, openFileWithDefaultApp, currentPath, contextMenuState]);

  const ensureEntry = useCallback(async (fullPath: string, defaultName: string): Promise<VfsEntry | null> => {
    const cached = statCacheRef.current.get(fullPath);
    if (cached) {
      return { ...cached, name: cached.name || defaultName };
    }
    try {
      const stat = await vfsApi.stat(fullPath);
      const entry: VfsEntry = {
        name: (stat as any)?.name || defaultName,
        is_dir: Boolean((stat as any)?.is_dir),
        size: Number((stat as any)?.size ?? 0),
        mtime: Number((stat as any)?.mtime ?? (stat as any)?.mtime_ms ?? 0),
        type: (stat as any)?.type,
        has_thumbnail: Boolean((stat as any)?.has_thumbnail),
      };
      statCacheRef.current.set(fullPath, entry);
      return entry;
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('Load failed');
      message.error(msg);
      return null;
    }
  }, [t]);

  const handleResultContextMenu = useCallback(async (event: React.MouseEvent, item: SearchResultItem) => {
    event.preventDefault();
    closeContextMenu();
    const rawPath = (item.path || '').replace(/\/+$/, '');
    if (!rawPath) {
      return;
    }
    const normalizedPath = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
    const segments = normalizedPath.split('/').filter(Boolean);
    const filename = segments.pop() || '';
    const dir = segments.length ? `/${segments.join('/')}` : '/';
    const entry = await ensureEntry(normalizedPath, filename);
    if (!entry) return;
    setCurrentPath(dir || '/');
    setMenuEntries([entry]);
    setSelectedEntryNames([entry.name]);
    setContextMenuState({
      entry,
      x: event.clientX,
      y: event.clientY,
      path: dir || '/',
    });
  }, [closeContextMenu, ensureEntry]);

  const performSearch = async (options?: { page?: number; mode?: SearchMode }) => {
    const query = search.trim();
    if (!query) {
      setSearched(false);
      setResults([]);
      setHasMore(false);
      return;
    }

    const currentMode = options?.mode ?? searchMode;
    const targetPage = currentMode === 'filename' ? (options?.page ?? (currentMode === searchMode ? page : 1)) : 1;

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    setLoading(true);
    closeContextMenu();
    setSearched(true);
    if (currentMode === 'filename') {
      setPage(targetPage);
    } else {
      setPage(1);
      setHasMore(false);
    }

    try {
      const res = await vfsApi.searchFiles(
        query,
        currentMode === 'filename' ? PAGE_SIZE : 10,
        currentMode,
        currentMode === 'filename' ? targetPage : undefined,
        currentMode === 'filename' ? PAGE_SIZE : undefined,
      );
      if (requestId !== requestIdRef.current) {
        return;
      }
      setResults(res.items);
      if (currentMode === 'filename') {
        const pagination = res.pagination;
        setHasMore(Boolean(pagination?.has_more));
        if (pagination?.page) {
          setPage(pagination.page);
        }
      } else {
        setHasMore(false);
      }
    } catch {
      if (requestId !== requestIdRef.current) {
        return;
      }
      setResults([]);
      if (currentMode === 'filename') {
        setHasMore(false);
      }
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  };

  const handleSearch = () => {
    if (!search.trim()) {
      closeContextMenu();
      setResults([]);
      setSearched(false);
      setHasMore(false);
      setPage(1);
      return;
    }
    void performSearch({ page: searchMode === 'filename' ? 1 : undefined });
  };

  const handleModeChange = (value: string | number) => {
    const nextMode = value as SearchMode;
    setHasMore(false);
    setPage(1);
    setSearchMode(nextMode);
    closeContextMenu();
    if (search.trim()) {
      void performSearch({ mode: nextMode, page: nextMode === 'filename' ? 1 : undefined });
    } else {
      setResults([]);
      setSearched(false);
    }
  };

  const totalItems = searchMode === 'filename'
    ? (hasMore ? page * PAGE_SIZE + 1 : (page - 1) * PAGE_SIZE + results.length)
    : results.length;

  return (
    <Modal
      open={open}
      onCancel={handleClose}
      footer={null}
      width={720}
      centered
      title={null}
      closable={false}
      styles={{
        body: {
          padding: '12px 16px 16px',
          maxHeight: '70vh',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        },
      }}
    >
      <Flex vertical style={{ gap: 12, flex: 1, minHeight: 0 }}>
        <Flex align="center" style={{ width: '100%', gap: 12, flexWrap: 'wrap' }}>
          <Segmented
            options={[
              { label: t('Smart Search'), value: 'vector' },
              { label: t('Name Search'), value: 'filename' },
            ]}
            value={searchMode}
            onChange={handleModeChange}
            style={{
              minWidth: 160,
              height: 40,
              borderRadius: 20,
              display: 'flex',
              alignItems: 'center',
            }}
            size="large"
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder={t('Search files / tags / types')}
            value={search}
            onChange={e => {
              const value = e.target.value;
              setSearch(value);
              if (!value.trim()) {
                setResults([]);
                setSearched(false);
                setHasMore(false);
                setPage(1);
                requestIdRef.current += 1;
                setLoading(false);
              }
            }}
            style={{ fontSize: 18, height: 40, flex: 1, minWidth: 240 }}
            styles={{
              input: {
                borderRadius: 20,
              },
            }}
            autoFocus
            onPressEnter={handleSearch}
          />
        </Flex>

        {!searched ? null : (
          <Flex vertical style={{ flex: 1, minHeight: 0 }}>
            <Divider style={{ margin: 0, padding: '0 0 12px' }}>{t('Search Results')}</Divider>
            {loading ? (
              <Flex align="center" justify="center" style={{ flex: 1 }}>
                <Spin />
              </Flex>
            ) : results.length === 0 ? (
              <Flex align="center" justify="center" style={{ flex: 1 }}>
                <Empty description={t('No files found')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
              </Flex>
            ) : (
              <div style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
                <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', paddingRight: 6 }}>
                  <List
                    itemLayout="horizontal"
                    dataSource={results}
                    split={false}
                    renderItem={item => {
                      const fullPath = item.path || '';
                      const trimmed = fullPath.replace(/\/+$/, '');
                      const parts = trimmed.split('/');
                      const filename = parts.pop() || '';
                      const dir = parts.length ? '/' + parts.join('/') : '/';
                    const snippet = item.snippet || '';
                      const retrieval = item.metadata?.retrieval_source || item.source_type;
                      const retrievalLabel = renderSourceLabel(retrieval);
                      const scoreText = Number.isFinite(item.score) ? item.score.toFixed(2) : '-';

                      return (
                        <List.Item
                          style={{ padding: '10px 12px', borderRadius: 6, background: '#fafafa', marginBottom: 8 }}
                          onContextMenu={(event) => { void handleResultContextMenu(event, item); }}
                        >
                          <List.Item.Meta
                            avatar={<FileTextOutlined style={{ fontSize: 18, color: '#8c8c8c' }} />}
                            title={
                              <a
                                onClick={() => {
                                  navigate(`/files${dir === '/' ? '' : dir}`, { state: { highlight: { name: filename } } });
                                  handleClose();
                                }}
                                style={{ fontSize: 16 }}
                              >
                                {fullPath}
                              </a>
                            }
                            description={(
                              <Space direction="vertical" size={6} style={{ width: '100%' }}>
                                {snippet ? (
                                  <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0 }}>
                                    {snippet}
                                  </Typography.Paragraph>
                                ) : null}
                                <Space size={10} wrap>
                                  {retrieval ? (
                                    <Tag color={sourceColor(retrieval)} style={{ marginRight: 0 }}>
                                      {retrievalLabel}
                                    </Tag>
                                  ) : null}
                                  <Typography.Text type="secondary">
                                    {t('Relevance')}: {scoreText}
                                  </Typography.Text>
                                </Space>
                              </Space>
                            )}
                          />
                        </List.Item>
                      );
                    }}
                  />
                </div>
                {searchMode === 'filename' && results.length > 0 ? (
                  <Pagination
                    current={page}
                    pageSize={PAGE_SIZE}
                    total={Math.max(totalItems, 1)}
                    showSizeChanger={false}
                    size="small"
                    style={{ marginTop: 12, textAlign: 'right' }}
                    onChange={(nextPage) => {
                      void performSearch({ page: nextPage });
                    }}
                  />
                ) : null}
              </div>
            )}
          </Flex>
        )}
      </Flex>
      {contextMenuState ? (
        <ContextMenu
          x={contextMenuState.x}
          y={contextMenuState.y}
          entry={contextMenuState.entry}
          entries={menuEntries}
          selectedEntries={selectedEntryNames}
          processorTypes={processorTypes}
          onClose={closeContextMenu}
          onOpen={handleOpenEntry}
          onOpenWith={(entry, appKey) => confirmOpenWithApp(entry, appKey, contextMenuState?.path ?? currentPath)}
          onDownload={doDownload}
          onRename={setRenaming}
          onDelete={(entriesToDelete) => doDelete(entriesToDelete)}
          onDetail={openDetail}
          onProcess={(entry, type) => {
            processorHook.setSelectedProcessor(type);
            processorHook.openProcessorModal(entry);
          }}
          onUploadFile={noop}
          onUploadDirectory={noop}
          onCreateDir={noop}
          onShare={doShare}
          onGetDirectLink={doGetDirectLink}
          onMove={(entriesToMove) => setMovingEntries(entriesToMove)}
          onCopy={(entriesToCopy) => setCopyingEntries(entriesToCopy)}
        />
      ) : null}
      <RenameModal
        entry={renaming}
        onOk={(entry, newName) => {
          void doRename(entry, newName);
          setRenaming(null);
        }}
        onCancel={() => setRenaming(null)}
      />
      <FileDetailModal
        entry={detailEntry}
        loading={detailLoading}
        data={detailData}
        onClose={() => setDetailEntry(null)}
      />
      <MoveCopyModal
        mode="move"
        entries={movingEntries}
        open={movingEntries.length > 0}
        defaultPath={buildDefaultDestination(movingEntries)}
        onOk={async (destination) => {
          if (movingEntries.length > 0) {
            await doMove(movingEntries, destination);
          }
        }}
        onCancel={() => setMovingEntries([])}
      />
      <MoveCopyModal
        mode="copy"
        entries={copyingEntries}
        open={copyingEntries.length > 0}
        defaultPath={buildDefaultDestination(copyingEntries)}
        onOk={async (destination) => {
          if (copyingEntries.length > 0) {
            await doCopy(copyingEntries, destination);
          }
        }}
        onCancel={() => setCopyingEntries([])}
      />
      {sharingEntries.length > 0 ? (
        <ShareModal
          path={currentPath}
          entries={sharingEntries}
          open={sharingEntries.length > 0}
          onOk={() => setSharingEntries([])}
          onCancel={() => setSharingEntries([])}
        />
      ) : null}
      <DirectLinkModal
        entry={directLinkEntry}
        path={currentPath}
        open={!!directLinkEntry}
        onCancel={() => setDirectLinkEntry(null)}
      />
      <ProcessorModal
        entry={processorHook.processorModal.entry}
        visible={processorHook.processorModal.visible}
        loading={processorHook.processorLoading}
        processorTypes={processorTypes}
        selectedProcessor={processorHook.selectedProcessor}
        config={processorHook.processorConfig}
        savingPath={processorHook.processorSavingPath}
        overwrite={processorHook.processorOverwrite}
        onOk={processorHook.handleProcessorOk}
        onCancel={processorHook.handleProcessorCancel}
        onSelectedProcessorChange={processorHook.setSelectedProcessor}
        onConfigChange={processorHook.setProcessorConfig}
        onSavingPathChange={processorHook.setProcessorSavingPath}
        onOverwriteChange={processorHook.setProcessorOverwrite}
      />
    </Modal>
  );
};

export default SearchDialog;
