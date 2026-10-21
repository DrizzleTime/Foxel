import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { Button, Space, theme, Pagination } from 'antd';
import { useFileExplorer } from './hooks/useFileExplorer';
import { useFileSelection } from './hooks/useFileSelection';
import { useFileActions } from './hooks/useFileActions.tsx';
import { useAppWindows } from '../../contexts/AppWindowsContext';
import { useContextMenu } from './hooks/useContextMenu';
import { useProcessor } from './hooks/useProcessor';
import { useFileSearch } from './hooks/useFileSearch';
import { useThumbnails } from './hooks/useThumbnails';
import { useUploader } from './hooks/useUploader';
import { useBatchMode, type BatchItem } from './hooks/useBatchMode';
import { Header } from './components/Header';
import { GridView } from './components/GridView';
import { FileListView } from './components/FileListView';
import { EmptyState } from './components/EmptyState';
import { ContextMenu } from './components/ContextMenu';
import { DropzoneOverlay } from './components/DropzoneOverlay';
import { CreateDirModal } from './components/Modals/CreateDirModal';
import { CreateFileModal } from './components/Modals/CreateFileModal';
import { RenameModal } from './components/Modals/RenameModal';
import { CompressModal } from './components/Modals/CompressModal';
import { ExtractModal } from './components/Modals/ExtractModal';
import { ProcessorModal } from './components/Modals/ProcessorModal';
import UploadModal from './components/Modals/UploadModal';
import { ShareModal } from './components/Modals/ShareModal';
import { DirectLinkModal } from './components/Modals/DirectLinkModal';
import { VideoRoomModal } from './components/Modals/VideoRoomModal';
import { BatchActionBar } from './components/BatchActionBar';
import { BatchProgressModal } from './components/Modals/BatchProgressModal';
import { FileDetailModal } from './components/FileDetailModal';
import { MoveCopyModal } from './components/Modals/MoveCopyModal';
import { SearchResultsView } from './components/SearchResultsView';
import type { ViewMode } from './types';
import { vfsApi, type VfsEntry } from '../../api/client';
import type { BatchOpResult } from '../../api/vfs';
import { getPublicConfig } from '../../api/config';
import { LoadingSkeleton } from './components/LoadingSkeleton';
import useResponsive from '../../hooks/useResponsive';

const FileExplorerPage = memo(function FileExplorerPage() {
  const { navKey = 'files', '*': restPath = '' } = useParams();
  const { token } = theme.useToken();
  const { isMobile } = useResponsive();
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [isDragging, setIsDragging] = useState(false);
  const [showSkeleton, setShowSkeleton] = useState(false);
  const dragCounter = useRef(0);
  const skeletonTimerRef = useRef<number | null>(null);

  // --- Hooks ---
  const { path, entries, loading, pagination, processorTypes, sortBy, sortOrder, load, navigateTo, goUp, handlePaginationChange, refresh, handleSortChange, goCursorNext, goCursorPrev } = useFileExplorer(navKey);
  const { selectedEntries, handleSelect, handleSelectRange, clearSelection, setSelectedEntries } = useFileSelection();
  const batch = useBatchMode(path);
  const { openFileWithDefaultApp, confirmOpenWithApp } = useAppWindows();
  const { ctxMenu, blankCtxMenu, openContextMenu, openBlankContextMenu, openContextMenuAt, closeContextMenus } = useContextMenu();
  const uploader = useUploader(path, refresh);
  const { handleFileDrop, openFilePicker, openDirectoryPicker, handleFileInputChange, handleDirectoryInputChange } = uploader;
  const { thumbs } = useThumbnails(entries, path);

  // --- State for Modals ---
  const [creatingDir, setCreatingDir] = useState(false);
  const [creatingFile, setCreatingFile] = useState(false);
  const [renaming, setRenaming] = useState<VfsEntry | null>(null);
  const [sharingEntries, setSharingEntries] = useState<VfsEntry[]>([]);
  const [detailEntry, setDetailEntry] = useState<VfsEntry | null>(null);
  const [directLinkEntry, setDirectLinkEntry] = useState<VfsEntry | null>(null);
  const [videoRoomEntry, setVideoRoomEntry] = useState<VfsEntry | null>(null);
  const [detailData, setDetailData] = useState<Record<string, unknown> | { error: string } | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [movingEntries, setMovingEntries] = useState<VfsEntry[]>([]);
  const [copyingEntries, setCopyingEntries] = useState<VfsEntry[]>([]);
  const [compressingEntries, setCompressingEntries] = useState<VfsEntry[]>([]);
  const [compressionCapability, setCompressionCapability] = useState<{ path: string; supported: boolean } | null>(null);
  const [extractingEntry, setExtractingEntry] = useState<VfsEntry | null>(null);
  const [extractionCapability, setExtractionCapability] = useState<{ path: string; supported: boolean } | null>(null);
  const [pendingBatchItems, setPendingBatchItems] = useState<BatchItem[] | null>(null);
  const [batchCompressSources, setBatchCompressSources] = useState<string[] | null>(null);

  // --- Search ---
  const fileSearch = useFileSearch({
    currentPath: path,
    navigateTo,
    openFileWithDefaultApp,
    openContextMenu,
    closeContextMenus,
    activeEntry: ctxMenu?.entry ?? null,
  });

  const {
    isSearching,
    actionPath,
    loading: searchLoading,
    query: searchQuery,
    displayItems: searchItems,
    selectedPaths: searchSelectedPaths,
    selectedNames: searchSelectedNames,
    contextEntries: searchContextEntries,
    entrySnapshot: searchEntrySnapshot,
    clearSearchParams,
    refreshSearch,
    openResult: openSearchResult,
    selectResult: selectSearchResult,
    openResultContextMenu: openSearchContextMenu,
    openResultContextMenuAt: openSearchContextMenuAt,
    clearSelection: clearSearchSelection,
  } = fileSearch;

  const entryBasePath = isSearching ? actionPath : path;

  useEffect(() => {
    if (!ctxMenu) return;
    let active = true;
    vfsApi.compressionCapabilities(entryBasePath)
      .then(capability => {
        if (active) setCompressionCapability({ path: entryBasePath, supported: capability.formats.includes('zip') });
      })
      .catch(() => {
        if (active) setCompressionCapability({ path: entryBasePath, supported: false });
      });
    return () => { active = false; };
  }, [ctxMenu, entryBasePath]);

  useEffect(() => {
    if (!ctxMenu || ctxMenu.entry.is_dir || !/\.zip$/i.test(ctxMenu.entry.name)) return;
    let active = true;
    vfsApi.extractionCapabilities(entryBasePath)
      .then(capability => {
        if (active) setExtractionCapability({ path: entryBasePath, supported: capability.formats.includes('zip') });
      })
      .catch(() => {
        if (active) setExtractionCapability({ path: entryBasePath, supported: false });
      });
    return () => { active = false; };
  }, [ctxMenu, entryBasePath]);

  // --- Effects ---
  const routePath = '/' + (restPath || '').replace(/^\/+/, '');

  useEffect(() => {
    load(routePath, 1, pagination.pageSize, sortBy, sortOrder);
  }, [routePath, navKey, load, pagination.pageSize, sortBy, sortOrder]);

  useEffect(() => {
    let mounted = true;
    getPublicConfig()
      .then((cfg) => {
        if (!mounted) return;
        setViewMode(cfg.DEFAULT_FILE_VIEW_MODE === 'list' ? 'list' : 'grid');
      })
      .catch(() => {
        if (mounted) setViewMode('grid');
      });
    return () => {
      mounted = false;
    };
  }, []);

  const effectiveRefresh = useCallback(() => {
    if (isSearching) {
      refreshSearch();
      return;
    }
    refresh();
  }, [isSearching, refresh, refreshSearch]);

  useEffect(() => {
    if (skeletonTimerRef.current !== null) {
      clearTimeout(skeletonTimerRef.current);
      skeletonTimerRef.current = null;
    }

    if (loading) {
      skeletonTimerRef.current = window.setTimeout(() => {
        setShowSkeleton(true);
        skeletonTimerRef.current = null;
      }, 200);
    } else {
      setShowSkeleton(false);
    }

    return () => {
      if (skeletonTimerRef.current !== null) {
        clearTimeout(skeletonTimerRef.current);
        skeletonTimerRef.current = null;
      }
    };
  }, [loading]);

  // --- Handlers ---
  const clearAllSelection = useCallback(() => {
    clearSelection();
    clearSearchSelection();
  }, [clearSearchSelection, clearSelection]);

  const removeBatchPaths = batch.removePaths;
  const handleBatchResult = useCallback((result: BatchOpResult) => {
    removeBatchPaths(result.results.filter(item => item.ok).map(item => item.src));
  }, [removeBatchPaths]);

  const { doCreateDir: doCreateDirInCurrentDir, doCreateFile: doCreateFileInCurrentDir } = useFileActions({
    path,
    refresh,
    clearSelection,
    onShare: (entriesToShare) => setSharingEntries(entriesToShare),
    onGetDirectLink: (entry) => setDirectLinkEntry(entry),
  });

  const { doDelete, doRename, doDownload, doShare, doGetDirectLink, doMove, doCopy,
    doBatchDelete, doBatchTransfer, batchProgress, closeBatchProgress } = useFileActions({
    path: entryBasePath,
    refresh: effectiveRefresh,
    clearSelection: clearAllSelection,
    onBatchResult: handleBatchResult,
    onShare: (entriesToShare) => setSharingEntries(entriesToShare),
    onGetDirectLink: (entry) => setDirectLinkEntry(entry),
  });

  const processorHook = useProcessor({ path: entryBasePath, processorTypes, refresh: effectiveRefresh });

  const handleOpenEntry = (entry: VfsEntry) => {
    if (entry.is_dir) {
      const next = (entryBasePath === '/' ? '' : entryBasePath) + '/' + entry.name;
      navigateTo(next.replace(/\/+/g, '/'));
    } else {
      openFileWithDefaultApp(entry, entryBasePath);
    }
  };

  const openDetail = async (entry: VfsEntry) => {
    setDetailEntry(entry);
    setDetailLoading(true);
    try {
      const fullPath = (entryBasePath === '/' ? '' : entryBasePath) + '/' + entry.name;
      const stat = await vfsApi.stat(fullPath, { verbose: true });
      setDetailData(stat as Record<string, unknown>);
    } catch (error) {
      const messageText = error instanceof Error ? error.message : String(error);
      setDetailData({ error: messageText });
    } finally {
      setDetailLoading(false);
    }
  };

  const buildDefaultDestination = useCallback((targetEntries: VfsEntry[]) => {
    if (!targetEntries || targetEntries.length === 0) return '';
    if (targetEntries.length > 1) {
      return entryBasePath || '/';
    }
    const entry = targetEntries[0];
    const base = entryBasePath === '/' ? '' : entryBasePath;
    const segments = [base, entry.name].filter(Boolean);
    const joined = segments.join('/');
    if (!joined) {
      return '/';
    }
    return joined.startsWith('/') ? joined : `/${joined}`;
  }, [entryBasePath]);

  // --- Batch mode (touch) ---
  const batchBarVisible = isMobile && batch.active && !isSearching;
  const batchSelectableEntries = entries.filter(e => e.type !== 'mount');
  const batchAllSelected = batchSelectableEntries.length > 0
    && batchSelectableEntries.every(e => batch.currentDirNames.has(e.name));
  const batchCanShare = batch.items.every(i => (i.path.slice(0, i.path.lastIndexOf('/')) || '/') === path);

  const batchToEntries = useCallback((items: BatchItem[]): VfsEntry[] =>
    items.map(i => ({ name: i.name, is_dir: i.isDir, size: i.size, mtime: i.mtime })),
  []);

  const batchExit = batch.exit;
  useEffect(() => {
    if (isSearching) batchExit();
  }, [isSearching, batchExit]);

  const handleBatchToggle = useCallback((entry: VfsEntry) => {
    if (entry.type === 'mount') return;
    batch.toggle(entry);
  }, [batch]);

  const handleBatchToggleAll = useCallback(() => {
    batch.toggleMany(batchSelectableEntries);
  }, [batch, batchSelectableEntries]);

  const handleBatchDelete = useCallback(() => {
    doBatchDelete(batch.items);
  }, [batch.items, doBatchDelete]);

  const handleBatchCompress = useCallback(() => {
    setBatchCompressSources(batch.items.map(i => i.path));
  }, [batch.items]);

  const handleBatchShare = useCallback(() => {
    const currentDirItems = batch.items.filter(i => (i.path.slice(0, i.path.lastIndexOf('/')) || '/') === path);
    if (currentDirItems.length === 0) return;
    doShare(batchToEntries(currentDirItems));
  }, [batch.items, path, doShare, batchToEntries]);

  const handleBatchMove = useCallback(() => {
    setPendingBatchItems(batch.items);
    setMovingEntries(batchToEntries(batch.items));
  }, [batch.items, batchToEntries]);

  const handleBatchCopy = useCallback(() => {
    setPendingBatchItems(batch.items);
    setCopyingEntries(batchToEntries(batch.items));
  }, [batch.items, batchToEntries]);

  const closeBatchModals = useCallback(() => {
    setPendingBatchItems(null);
    setMovingEntries([]);
    setCopyingEntries([]);
  }, []);

  const showFsPagination = !isSearching && pagination.mode === 'paged' && pagination.total > 0;
  const showCursorPagination = !isSearching && pagination.mode === 'cursor' && (pagination.cursorHistory.length > 0 || pagination.hasNext);
  const shouldReserveBottomBar = showFsPagination;
  const shouldReserveAnyBottomBar = shouldReserveBottomBar || showCursorPagination;

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current++;
    if (e.dataTransfer.items && e.dataTransfer.items.length > 0) {
      setIsDragging(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounter.current--;
    if (dragCounter.current === 0) {
      setIsDragging(false);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;
    void handleFileDrop(e.dataTransfer);
  };

  const getAnchorPoint = useCallback((anchor: HTMLElement) => {
    const rect = anchor.getBoundingClientRect();
    return {
      x: Math.min(rect.right, window.innerWidth - 24),
      y: Math.min(rect.bottom + 8, window.innerHeight - 24),
    };
  }, []);

  const openEntryMenuFromAnchor = useCallback((entry: VfsEntry, anchor: HTMLElement) => {
    const point = getAnchorPoint(anchor);
    openContextMenuAt(entry, point.x, point.y);
  }, [getAnchorPoint, openContextMenuAt]);

  const openSearchMenuFromAnchor = useCallback((fullPath: string, anchor: HTMLElement) => {
    const point = getAnchorPoint(anchor);
    void openSearchContextMenuAt(point.x, point.y, fullPath);
  }, [getAnchorPoint, openSearchContextMenuAt]);

  return (
    <div
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadius,
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        position: 'relative'
      }}
      onClick={closeContextMenus}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <Header
        navKey={navKey}
        path={path}
        loading={isSearching ? searchLoading : loading}
        viewMode={viewMode}
        sortBy={sortBy}
        sortOrder={sortOrder}
        paginationMode={pagination.mode}
        isMobile={isMobile}
        batchMode={batchBarVisible}
        batchCount={batch.count}
        batchAllSelected={batchAllSelected}
        onBatchEnter={batch.enter}
        onBatchExit={batch.exit}
        onBatchToggleAll={handleBatchToggleAll}
        onGoUp={goUp}
        onNavigate={navigateTo}
        onRefresh={effectiveRefresh}
        onCreateDir={() => setCreatingDir(true)}
        onCreateFile={() => setCreatingFile(true)}
        onUploadFile={openFilePicker}
        onUploadDirectory={openDirectoryPicker}
        onSetViewMode={setViewMode}
        onSortChange={handleSortChange}
      />

      <input
        ref={uploader.fileInputRef}
        type="file"
        style={{ display: 'none' }}
        multiple
        onChange={handleFileInputChange}
      />
      <input
        ref={uploader.directoryInputRef}
        type="file"
        style={{ display: 'none' }}
        multiple
        onChange={handleDirectoryInputChange}
      />

      <div style={{ flex: 1, overflow: 'auto', minHeight: 0, paddingBottom: batchBarVisible ? 0 : shouldReserveAnyBottomBar ? '80px' : '0' }} onContextMenu={isMobile ? undefined : openBlankContextMenu}>
        {isSearching ? (
          <SearchResultsView
            viewMode={viewMode}
            loading={searchLoading}
            query={searchQuery}
            items={searchItems}
            warnings={fileSearch.warnings}
            selectedPaths={searchSelectedPaths}
            entrySnapshot={searchEntrySnapshot}
            mobile={isMobile}
            onClearSearch={clearSearchParams}
            onSelect={selectSearchResult}
            onOpen={(fullPath) => { void openSearchResult(fullPath); }}
            onContextMenu={(e, fullPath) => { void openSearchContextMenu(e, fullPath); }}
            onOpenMenu={openSearchMenuFromAnchor}
          />
        ) : showSkeleton && loading && (entries.length === 0 || path !== routePath) ? (
          <LoadingSkeleton mode={viewMode} />
        ) : !loading && entries.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}><EmptyState isRoot={path === '/'} /></div>
        ) : viewMode === 'grid' ? (
          <GridView
            entries={entries}
            thumbs={thumbs}
            selectedEntries={selectedEntries}
            path={path}
            mobile={isMobile}
            onSelect={handleSelect}
            onSelectRange={handleSelectRange}
            onOpen={handleOpenEntry}
            onContextMenu={openContextMenu}
            onOpenMenu={openEntryMenuFromAnchor}
            batchMode={batchBarVisible}
            batchSelectedNames={batch.currentDirNames}
            onBatchToggle={handleBatchToggle}
          />
        ) : (
          <FileListView
            entries={entries}
            mobile={isMobile}
            thumbs={thumbs}
            selectedEntries={selectedEntries}
            onRowClick={(r, e) => handleSelect(r, e.ctrlKey || e.metaKey)}
            onSelectionChange={setSelectedEntries}
            onOpen={handleOpenEntry}
            onOpenWith={(entry, appKey) => confirmOpenWithApp(entry, appKey, path)}
            onRename={setRenaming}
            onDelete={(entry) => doDelete([entry])}
            onContextMenu={openContextMenu}
            onOpenMenu={openEntryMenuFromAnchor}
            batchMode={batchBarVisible}
            batchSelectedNames={batch.currentDirNames}
            onBatchToggle={handleBatchToggle}
          />
        )}
      </div>

      {showFsPagination && (
        <div style={{ position: batchBarVisible ? 'relative' : 'absolute', flexShrink: 0, bottom: 0, left: 0, right: 0, padding: '12px 16px', background: token.colorBgContainer, borderTop: `1px solid ${token.colorBorderSecondary}`, textAlign: 'center', zIndex: 10 }}>
          <Pagination {...pagination} onChange={handlePaginationChange} onShowSizeChange={handlePaginationChange} />
        </div>
      )}

      {showCursorPagination && (
        <div style={{ position: batchBarVisible ? 'relative' : 'absolute', flexShrink: 0, bottom: 0, left: 0, right: 0, padding: '12px 16px', background: token.colorBgContainer, borderTop: `1px solid ${token.colorBorderSecondary}`, textAlign: 'center', zIndex: 10 }}>
          <Space>
            <Button size="small" onClick={goCursorPrev} disabled={pagination.cursorHistory.length === 0 || loading}>
              上一页
            </Button>
            <Button size="small" type="primary" onClick={goCursorNext} disabled={!pagination.hasNext || loading}>
              下一页
            </Button>
          </Space>
        </div>
      )}

      {/* --- Modals & Context Menus --- */}
      <CreateDirModal open={creatingDir} onOk={(name) => { doCreateDirInCurrentDir(name); setCreatingDir(false); }} onCancel={() => setCreatingDir(false)} />
      <CreateFileModal open={creatingFile} onOk={(name) => { doCreateFileInCurrentDir(name); setCreatingFile(false); }} onCancel={() => setCreatingFile(false)} />
      <RenameModal entry={renaming} onOk={(entry, newName) => { doRename(entry, newName); setRenaming(null); }} onCancel={() => setRenaming(null)} />
      <FileDetailModal entry={detailEntry} loading={detailLoading} data={detailData} onClose={() => setDetailEntry(null)} />
      <MoveCopyModal
        mode="move"
        entries={movingEntries}
        open={movingEntries.length > 0}
        defaultPath={pendingBatchItems ? path : buildDefaultDestination(movingEntries)}
        destinationIsDirectory={!!pendingBatchItems}
        onOk={async (destination) => {
          if (pendingBatchItems && movingEntries.length > 0) {
            await doBatchTransfer(pendingBatchItems, destination, 'move');
            closeBatchModals();
          } else if (movingEntries.length > 0) {
            await doMove(movingEntries, destination);
          }
        }}
        onCancel={() => {
          closeBatchModals();
        }}
      />
      <MoveCopyModal
        mode="copy"
        entries={copyingEntries}
        open={copyingEntries.length > 0}
        defaultPath={pendingBatchItems ? path : buildDefaultDestination(copyingEntries)}
        destinationIsDirectory={!!pendingBatchItems}
        onOk={async (destination) => {
          if (pendingBatchItems && copyingEntries.length > 0) {
            await doBatchTransfer(pendingBatchItems, destination, 'copy');
            closeBatchModals();
          } else if (copyingEntries.length > 0) {
            await doCopy(copyingEntries, destination);
          }
        }}
        onCancel={() => {
          closeBatchModals();
        }}
      />
      {sharingEntries.length > 0 && (
        <ShareModal
          path={entryBasePath}
          entries={sharingEntries}
          open={sharingEntries.length > 0}
          onOk={() => setSharingEntries([])}
          onCancel={() => setSharingEntries([])}
        />
      )}
      <DirectLinkModal
        entry={directLinkEntry}
        path={entryBasePath}
        open={!!directLinkEntry}
        onCancel={() => setDirectLinkEntry(null)}
      />
      <VideoRoomModal
        entry={videoRoomEntry}
        path={entryBasePath}
        open={!!videoRoomEntry}
        onCancel={() => setVideoRoomEntry(null)}
      />
      <ProcessorModal
        entries={processorHook.processorModal.entries}
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

      {(ctxMenu || blankCtxMenu) && (
        <ContextMenu
          x={ctxMenu?.x || blankCtxMenu!.x}
          y={ctxMenu?.y || blankCtxMenu!.y}
          mobile={isMobile}
          entry={ctxMenu?.entry}
          entries={isSearching ? searchContextEntries : entries}
          selectedEntries={isSearching ? searchSelectedNames : selectedEntries}
          processorTypes={processorTypes}
          canCompress={compressionCapability?.path === entryBasePath && compressionCapability.supported}
          onCompress={setCompressingEntries}
          canExtract={extractionCapability?.path === entryBasePath && extractionCapability.supported}
          onExtract={setExtractingEntry}
          onClose={closeContextMenus}
          onOpen={handleOpenEntry}
          onOpenWith={(entry, appKey) => confirmOpenWithApp(entry, appKey, entryBasePath)}
          onDownload={doDownload}
          onRename={setRenaming}
          onDelete={(entriesToDelete) => doDelete(entriesToDelete)}
          onDetail={openDetail}
          onProcess={(entriesToProcess, type) => {
            processorHook.openProcessorModal(entriesToProcess, type);
          }}
          onUploadFile={openFilePicker}
          onUploadDirectory={openDirectoryPicker}
          onCreateFile={() => setCreatingFile(true)}
          onCreateDir={() => setCreatingDir(true)}
          onShare={doShare}
          onCreateVideoRoom={setVideoRoomEntry}
          onGetDirectLink={doGetDirectLink}
          onMove={(entriesToMove) => setMovingEntries(entriesToMove)}
          onCopy={(entriesToCopy) => setCopyingEntries(entriesToCopy)}
        />
      )}
      <CompressModal
        entries={compressingEntries}
        path={entryBasePath}
        sources={batchCompressSources}
        onCancel={() => {
          setCompressingEntries([]);
          setBatchCompressSources(null);
        }}
        onDone={() => {
          setCompressingEntries([]);
          setBatchCompressSources(null);
          clearAllSelection();
          effectiveRefresh();
        }}
      />
      <ExtractModal
        entry={extractingEntry}
        path={entryBasePath}
        onCancel={() => setExtractingEntry(null)}
        onDone={() => {
          setExtractingEntry(null);
          clearAllSelection();
          effectiveRefresh();
        }}
      />
      <UploadModal
        visible={uploader.isModalVisible}
        files={uploader.files}
        isUploading={uploader.isUploading}
        totalProgress={uploader.totalProgress}
        totalFileBytes={uploader.totalFileBytes}
        uploadedFileBytes={uploader.uploadedFileBytes}
        conflict={uploader.conflict}
        onClose={uploader.closeModal}
        onStartUpload={uploader.startUpload}
        onRetryFailed={uploader.retryFailed}
        onCancelUpload={uploader.cancelUpload}
        onResolveConflict={uploader.confirmConflict}
      />
      <BatchProgressModal state={batchProgress} onClose={closeBatchProgress} />
      {batchBarVisible && (
        <BatchActionBar
          count={batch.count}
          canShare={batchCanShare}
          onCompress={handleBatchCompress}
          onMove={handleBatchMove}
          onCopy={handleBatchCopy}
          onShare={handleBatchShare}
          onDelete={handleBatchDelete}
        />
      )}
      <DropzoneOverlay visible={isDragging} />
    </div>
  );
});

export default FileExplorerPage;
