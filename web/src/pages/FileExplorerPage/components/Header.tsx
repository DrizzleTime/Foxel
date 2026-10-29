import React, { useEffect, useRef, useState } from 'react';
import { Flex, Typography, Divider, Button, Space, Tooltip, Segmented, Breadcrumb, Input, theme, Dropdown } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined, PlusOutlined, UploadOutlined, AppstoreOutlined, UnorderedListOutlined, MoreOutlined, FileAddOutlined, CheckSquareOutlined, CloseOutlined, EditOutlined } from '@ant-design/icons';
import { Select } from 'antd';
import { useI18n } from '../../../i18n';
import type { ViewMode } from '../types';

interface HeaderProps {
  navKey: string;
  path: string;
  loading: boolean;
  viewMode: ViewMode;
  sortBy: string;
  sortOrder: string;
  paginationMode?: 'paged' | 'cursor';
  isMobile?: boolean;
  actionsDisabled?: boolean;
  onGoUp: () => void;
  onNavigate: (path: string) => void;
  onRefresh: () => void;
  onCreateDir: () => void;
  onCreateFile: () => void;
  onUploadFile: () => void;
  onUploadDirectory: () => void;
  onSetViewMode: (mode: ViewMode) => void;
  onSortChange: (sortBy: string, sortOrder: string) => void;
  batchMode?: boolean;
  batchCount?: number;
  batchAllSelected?: boolean;
  onBatchEnter?: () => void;
  onBatchExit?: () => void;
  onBatchToggleAll?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  path,
  loading,
  viewMode,
  sortBy,
  sortOrder,
  paginationMode = 'paged',
  isMobile = false,
  actionsDisabled = false,
  onGoUp,
  onNavigate,
  onRefresh,
  onCreateDir,
  onCreateFile,
  onUploadFile,
  onUploadDirectory,
  onSetViewMode,
  onSortChange,
  batchMode = false,
  batchCount = 0,
  batchAllSelected = false,
  onBatchEnter,
  onBatchExit,
  onBatchToggleAll,
}) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const [editingPath, setEditingPath] = useState(false);
  const [pathInputValue, setPathInputValue] = useState('');
  const clickTimerRef = useRef<number | null>(null);
  const editButtonRef = useRef<HTMLButtonElement>(null);
  const pathEditorHeight = Math.max(32, token.fontSizeSM * token.lineHeight + token.paddingXXS * 2);

  useEffect(() => () => {
    if (clickTimerRef.current !== null) window.clearTimeout(clickTimerRef.current);
  }, []);

  const clearClickTimer = () => {
    if (clickTimerRef.current !== null) {
      window.clearTimeout(clickTimerRef.current);
      clickTimerRef.current = null;
    }
  };

  const scheduleNavigate = (nextPath: string) => {
    clearClickTimer();
    clickTimerRef.current = window.setTimeout(() => {
      onNavigate(nextPath);
      clickTimerRef.current = null;
    }, 250);
  };

  const handlePathEdit = () => {
    if (isMobile) return;
    clearClickTimer();
    setEditingPath(true);
    setPathInputValue(path);
  };

  const handlePathSubmit = () => {
    const trimmed = pathInputValue.trim();
    if (trimmed && trimmed !== path) {
      onNavigate(trimmed);
    }
    setEditingPath(false);
    window.requestAnimationFrame(() => editButtonRef.current?.focus());
  };

  const handlePathCancel = (restoreFocus = false) => {
    setEditingPath(false);
    setPathInputValue('');
    if (restoreFocus) window.requestAnimationFrame(() => editButtonRef.current?.focus());
  };
  const sortDisabled = paginationMode === 'cursor';

  const renderBreadcrumb = () => {
    if (editingPath) {
      return (
        <Input
          size="small"
          aria-label={t('Folder path')}
          value={pathInputValue}
          onChange={(e) => setPathInputValue(e.target.value)}
          onPressEnter={handlePathSubmit}
          onBlur={() => handlePathCancel()}
          onKeyDown={(e) => e.key === 'Escape' && handlePathCancel(true)}
          autoFocus
          style={{ flex: 1, height: pathEditorHeight, boxSizing: 'border-box' }}
        />
      );
    }

    const breadcrumbItems = [
      { key: 'root', title: <button type="button" className="fx-text-button fx-breadcrumb-button" aria-current={path === '/' ? 'page' : undefined} onClick={() => scheduleNavigate('/')}>{t('Home')}</button> },
      ...path.split('/').filter(Boolean).map((segment, index, arr) => {
        const segmentPath = '/' + arr.slice(0, index + 1).join('/');
        return {
          key: segmentPath,
          title: <button type="button" className="fx-text-button fx-breadcrumb-button" aria-current={segmentPath === path ? 'page' : undefined} onClick={() => scheduleNavigate(segmentPath)}>{segment}</button>,
        };
      }),
    ];

    return (
      <div
        style={{
          cursor: isMobile ? 'default' : 'text',
          padding: `${token.paddingXXS}px ${token.paddingXS}px`,
          borderRadius: token.borderRadius,
          transition: 'background-color 0.2s',
          flex: 1,
          overflow: 'hidden',
          height: pathEditorHeight,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          minWidth: 0,
        }}
        onMouseEnter={(e) => {
          if (!isMobile) e.currentTarget.style.backgroundColor = token.colorFillTertiary;
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
        }}
        onDoubleClick={handlePathEdit}
      >
        <Breadcrumb className="fx-file-breadcrumb" items={isMobile ? breadcrumbItems.slice(-1) : breadcrumbItems} separator="/" style={{ fontSize: token.fontSizeSM }} />
      </div>
    );
  };

  const mobileMoreItems = [
    {
      key: 'new-file',
      disabled: actionsDisabled,
      label: t('New File'),
      icon: <FileAddOutlined />,
      onClick: onCreateFile,
    },
    {
      key: 'upload-folder',
      disabled: actionsDisabled,
      label: t('Upload Folder'),
      icon: <UploadOutlined />,
      onClick: onUploadDirectory,
    },
    ...(onBatchEnter ? [{
      key: 'batch',
      disabled: actionsDisabled,
      label: t('Batch operations'),
      icon: <CheckSquareOutlined />,
      onClick: onBatchEnter,
    }] : []),
    {
      key: 'sort',
      label: t('Sort By') + `: ${t(sortBy === 'mtime' ? 'Modified Time' : sortBy === 'size' ? 'Size' : 'Name')}`,
      disabled: sortDisabled,
      children: [
        { key: 'sort-name', label: t('Name'), onClick: () => onSortChange('name', sortOrder) },
        { key: 'sort-size', label: t('Size'), onClick: () => onSortChange('size', sortOrder) },
        { key: 'sort-mtime', label: t('Modified Time'), onClick: () => onSortChange('mtime', sortOrder) },
      ],
    },
    {
      key: 'sort-order',
      label: sortOrder === 'asc' ? t('Ascending') : t('Descending'),
      icon: sortOrder === 'asc' ? <ArrowUpOutlined /> : <ArrowDownOutlined />,
      disabled: sortDisabled,
      onClick: () => onSortChange(sortBy, sortOrder === 'asc' ? 'desc' : 'asc'),
    },
  ];

  const uploadMenu = {
    items: [
      { key: 'file', label: t('Upload Files') },
      { key: 'folder', label: t('Upload Folder') },
    ],
    onClick: ({ key }: { key: string }) => {
      if (key === 'folder') {
        onUploadDirectory();
      } else {
        onUploadFile();
      }
    },
  };

  if (isMobile) {
    if (batchMode) {
      return (
        <Flex className="fx-file-toolbar" align="center" gap={6} style={{ padding: '10px 12px', borderBottom: `1px solid ${token.colorBorderSecondary}`, minWidth: 0 }}>
          <h1 className="fx-sr-only">{t('File Manager')}</h1>
          <Button size="small" icon={<CloseOutlined />} onClick={onBatchExit} aria-label={t('Exit batch mode')} />
          <Typography.Text strong style={{ flex: 1, minWidth: 0 }}>
            {t('Selected {n} items', { n: batchCount })}
          </Typography.Text>
          <Button size="small" onClick={onBatchToggleAll} disabled={actionsDisabled || !onBatchToggleAll}>
            {batchAllSelected ? t('Deselect all') : t('Select all')}
          </Button>
        </Flex>
      );
    }
    return (
      <Flex className="fx-file-toolbar" vertical gap={8} style={{ padding: '10px 12px', borderBottom: `1px solid ${token.colorBorderSecondary}`, minWidth: 0 }}>
        <h1 className="fx-sr-only">{t('File Manager')}</h1>
        <Flex align="center" gap={6} style={{ minWidth: 0 }}>
          <Button icon={<ArrowUpOutlined />} aria-label={t('Up')} onClick={onGoUp} disabled={path === '/'} />
          {renderBreadcrumb()}
          <Space size={4} style={{ flexShrink: 0 }}>
            <Button
              size="small"
              icon={viewMode === 'grid' ? <UnorderedListOutlined /> : <AppstoreOutlined />}
              onClick={() => onSetViewMode(viewMode === 'grid' ? 'list' : 'grid')}
              aria-label={t(viewMode === 'grid' ? 'List' : 'Grid')}
              title={t(viewMode === 'grid' ? 'List' : 'Grid')}
            />
            <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading} aria-label={t('Refresh')} />
            <Dropdown menu={{ items: mobileMoreItems }}>
              <Button size="small" icon={<MoreOutlined />} aria-label={t('More')} />
            </Dropdown>
          </Space>
        </Flex>
        <Flex gap={8} wrap>
          <Button icon={<PlusOutlined />} onClick={onCreateDir} disabled={actionsDisabled}>{t('New Folder')}</Button>
          <Button icon={<UploadOutlined />} onClick={onUploadFile} disabled={actionsDisabled}>{t('Upload Files')}</Button>
        </Flex>
      </Flex>
    );
  }

  return (
    <Flex className="fx-file-toolbar" vertical gap={12} style={{ padding: '10px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
      <Flex align="center" gap={8} style={{ minWidth: 0 }}>
        <Button size="small" icon={<ArrowUpOutlined />} aria-label={t('Up')} onClick={onGoUp} disabled={path === '/'} />
        <Typography.Title level={1} style={{ fontSize: token.fontSize, margin: 0, whiteSpace: 'nowrap' }}>{t('File Manager')}</Typography.Title>
        <Divider orientation="vertical" />
        {renderBreadcrumb()}
        <Tooltip title={t('Edit path')}>
          <Button ref={editButtonRef} size="small" icon={<EditOutlined />} aria-label={t('Edit path')} onClick={handlePathEdit} />
        </Tooltip>
      </Flex>

      <Flex align="center" justify="space-between" gap={8} style={{ flexWrap: 'wrap' }}>
        <Space size={8} wrap>
          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading} aria-label={t('Refresh')}>
            {t('Refresh')}
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={onCreateDir} disabled={actionsDisabled} aria-label={t('New Folder')}>
            {t('New Folder')}
          </Button>
          <Space.Compact size="small">
            <Button onClick={onUploadFile} disabled={actionsDisabled}>{t('Upload')}</Button>
            <Dropdown menu={uploadMenu} disabled={actionsDisabled}>
              <Button icon={<UploadOutlined />} disabled={actionsDisabled} aria-label={t('Upload options')} />
            </Dropdown>
          </Space.Compact>
        </Space>

        <Space size={8} wrap>
          <Select
            aria-label={t('Sort By')}
            size="small"
            value={sortBy}
            disabled={sortDisabled}
            onChange={(val) => onSortChange(val, sortOrder)}
            style={{ width: 112 }}
            options={[
              { value: 'name', label: t('Name') },
              { value: 'size', label: t('Size') },
              { value: 'mtime', label: t('Modified Time') },
            ]}
          />
          <Button
            size="small"
            disabled={sortDisabled}
            aria-label={sortOrder === 'asc' ? t('Sort descending') : t('Sort ascending')}
            title={sortOrder === 'asc' ? t('Sort descending') : t('Sort ascending')}
            icon={sortOrder === 'asc' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            onClick={() => onSortChange(sortBy, sortOrder === 'asc' ? 'desc' : 'asc')}
          />
          <Segmented
            size="small"
            value={viewMode}
            onChange={(value) => onSetViewMode(value as ViewMode)}
            options={[
              { label: <Tooltip title={t('Grid')}><span><AppstoreOutlined aria-hidden /><span className="fx-sr-only">{t('Grid')}</span></span></Tooltip>, value: 'grid' },
              { label: <Tooltip title={t('List')}><span><UnorderedListOutlined aria-hidden /><span className="fx-sr-only">{t('List')}</span></span></Tooltip>, value: 'list' },
            ]}
          />
        </Space>
      </Flex>
    </Flex>
  );
};
