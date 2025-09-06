import { memo, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { theme, Pagination } from 'antd';
import { AppWindowsLayer } from '../../apps/AppWindowsLayer';
import { useFileExplorer } from './hooks/useFileExplorer';
import { useFileSelection } from './hooks/useFileSelection';
import { useFileActions } from './hooks/useFileActions.tsx';
import { useAppWindows } from './hooks/useAppWindows.tsx';
import { useContextMenu } from './hooks/useContextMenu';
import { useProcessor } from './hooks/useProcessor';
import { useThumbnails } from './hooks/useThumbnails';
import { useUploader } from './hooks/useUploader';
import { Header } from './components/Header';
import { GridView } from './components/GridView';
import { FileListView } from './components/FileListView';
import { EmptyState } from './components/EmptyState';
import { ContextMenu } from './components/ContextMenu';
import { DropzoneOverlay } from './components/DropzoneOverlay';
import { CreateDirModal } from './components/Modals/CreateDirModal';
import { RenameModal } from './components/Modals/RenameModal';
import { ProcessorModal } from './components/Modals/ProcessorModal';
import UploadModal from './components/Modals/UploadModal';
import { ShareModal } from './components/Modals/ShareModal';
import { DirectLinkModal } from './components/Modals/DirectLinkModal';
import { FileDetailModal } from './components/FileDetailModal';
import type { ViewMode } from './types';
import { vfsApi, type VfsEntry } from '../../api/client';

const FileExplorerPage = memo(function FileExplorerPage() {
  const { navKey = 'files', '*': restPath = '' } = useParams();
  const { token } = theme.useToken();
  const [viewMode, setViewMode] = useState<ViewMode>('grid');
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  // --- Hooks ---
  const { path, entries, loading, pagination, processorTypes, sortBy, sortOrder, load, navigateTo, goUp, handlePaginationChange, refresh, handleSortChange } = useFileExplorer(navKey);
  const { selectedEntries, handleSelect, handleSelectRange, clearSelection, setSelectedEntries } = useFileSelection();
  const { doCreateDir, doDelete, doRename, doDownload, doShare, doGetDirectLink } = useFileActions({ path, refresh, clearSelection, onShare: (entries) => setSharingEntries(entries), onGetDirectLink: (entry) => setDirectLinkEntry(entry) });
  const { appWindows, openFileWithDefaultApp, confirmOpenWithApp, closeWindow, toggleMax, bringToFront, updateWindow } = useAppWindows(path);
  const { ctxMenu, blankCtxMenu, openContextMenu, openBlankContextMenu, closeContextMenus } = useContextMenu();
  const uploader = useUploader(path, refresh);
  const { handleFileDrop } = uploader;
  const processorHook = useProcessor({ path, processorTypes, refresh });
  const { thumbs } = useThumbnails(entries, path);

  // --- State for Modals ---
  const [creatingDir, setCreatingDir] = useState(false);
  const [renaming, setRenaming] = useState<VfsEntry | null>(null);
  const [sharingEntries, setSharingEntries] = useState<VfsEntry[]>([]);
  const [detailEntry, setDetailEntry] = useState<VfsEntry | null>(null);
  const [directLinkEntry, setDirectLinkEntry] = useState<VfsEntry | null>(null);
  const [detailData, setDetailData] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // --- Effects ---
  useEffect(() => {
    const routeP = '/' + (restPath || '').replace(/^\/+/, '');
    load(routeP, 1, pagination.pageSize);
  }, [restPath, navKey, load, pagination.pageSize]);

  // --- Handlers ---
  const handleOpenEntry = (entry: VfsEntry) => {
    if (entry.is_dir) {
      const next = (path === '/' ? '' : path) + '/' + entry.name;
      navigateTo(next.replace(/\/+/g, '/'));
    } else {
      openFileWithDefaultApp(entry);
    }
  };

  const openDetail = async (entry: VfsEntry) => {
    setDetailEntry(entry);
    setDetailLoading(true);
    try {
      const fullPath = (path === '/' ? '' : path) + '/' + entry.name;
      const stat = await vfsApi.stat(fullPath);
      setDetailData(stat);
    } catch (e: any) {
      setDetailData({ error: e.message });
    } finally {
      setDetailLoading(false);
    }
  };

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
    handleFileDrop(e.dataTransfer.files);
  };

  return (
    <div
      style={{
        background: token.colorBgContainer,
        border: `1px solid ${token.colorBorderSecondary}`,
        borderRadius: token.borderRadius,
        height: 'calc(100vh - 88px)',
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
        loading={loading}
        viewMode={viewMode}
        sortBy={sortBy}
        sortOrder={sortOrder}
        onGoUp={goUp}
        onNavigate={navigateTo}
        onRefresh={refresh}
        onCreateDir={() => setCreatingDir(true)}
        onUpload={uploader.openModal}
        onSetViewMode={setViewMode}
        onSortChange={handleSortChange}
      />

      <input ref={uploader.fileInputRef} type="file" style={{ display: 'none' }} multiple onChange={uploader.handleFileChange} />

      <div style={{ flex: 1, overflow: 'auto', paddingBottom: pagination.total > 0 ? '80px' : '0' }} onContextMenu={openBlankContextMenu}>
        {loading && entries.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40 }}><EmptyState isRoot={path === '/'} /></div>
        ) : viewMode === 'grid' ? (
          <GridView
            entries={entries}
            thumbs={thumbs}
            selectedEntries={selectedEntries}
            loading={loading}
            path={path}
            onSelect={handleSelect}
            onSelectRange={handleSelectRange}
            onOpen={handleOpenEntry}
            onContextMenu={openContextMenu}
          />
        ) : (
          <FileListView
            entries={entries}
            loading={loading}
            selectedEntries={selectedEntries}
            onRowClick={(r, e) => handleSelect(r, e.ctrlKey || e.metaKey)}
            onSelectionChange={setSelectedEntries}
            onOpen={handleOpenEntry}
            onOpenWith={(entry, appKey) => confirmOpenWithApp(entry, appKey)}
            onRename={setRenaming}
            onDelete={(entry) => doDelete([entry])}
            onContextMenu={openContextMenu}
          />
        )}
      </div>

      {pagination.total > 0 && (
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '12px 16px', background: token.colorBgContainer, borderTop: `1px solid ${token.colorBorderSecondary}`, textAlign: 'center', zIndex: 10 }}>
          <Pagination {...pagination} onChange={handlePaginationChange} onShowSizeChange={handlePaginationChange} />
        </div>
      )}

      {/* --- Modals & Context Menus --- */}
      <CreateDirModal open={creatingDir} onOk={(name) => { doCreateDir(name); setCreatingDir(false); }} onCancel={() => setCreatingDir(false)} />
      <RenameModal entry={renaming} onOk={(entry, newName) => { doRename(entry, newName); setRenaming(null); }} onCancel={() => setRenaming(null)} />
      <FileDetailModal entry={detailEntry} loading={detailLoading} data={detailData} onClose={() => setDetailEntry(null)} />
      {sharingEntries.length > 0 && (
        <ShareModal
          path={path}
          entries={sharingEntries}
          open={sharingEntries.length > 0}
          onOk={() => setSharingEntries([])}
          onCancel={() => setSharingEntries([])}
        />
      )}
      <DirectLinkModal
        entry={directLinkEntry}
        path={path}
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

      {(ctxMenu || blankCtxMenu) && (
        <ContextMenu
          x={ctxMenu?.x || blankCtxMenu!.x}
          y={ctxMenu?.y || blankCtxMenu!.y}
          entry={ctxMenu?.entry}
          entries={entries}
          selectedEntries={selectedEntries}
          processorTypes={processorTypes}
          onClose={closeContextMenus}
          onOpen={handleOpenEntry}
          onOpenWith={(entry, appKey) => confirmOpenWithApp(entry, appKey)}
          onDownload={doDownload}
          onRename={setRenaming}
          onDelete={(entriesToDelete) => doDelete(entriesToDelete)}
          onDetail={openDetail}
          onProcess={(entry, type) => {
            processorHook.setSelectedProcessor(type);
            processorHook.openProcessorModal(entry);
          }}
          onUpload={uploader.openModal}
          onCreateDir={() => setCreatingDir(true)}
          onShare={doShare}
          onGetDirectLink={doGetDirectLink}
        />
      )}
      <UploadModal
        visible={uploader.isModalVisible}
        files={uploader.files}
        onClose={uploader.closeModal}
        onStartUpload={uploader.startUpload}
      />
      <AppWindowsLayer windows={appWindows} onClose={closeWindow} onToggleMax={toggleMax} onBringToFront={bringToFront} onUpdateWindow={updateWindow} />
      <DropzoneOverlay visible={isDragging} />
    </div>
  );
});

export default FileExplorerPage;