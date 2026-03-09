import React, { useRef, useState } from 'react';
import { Flex, Typography, Divider, Button, Space, Tooltip, Segmented, Breadcrumb, Input, theme, Dropdown } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined, PlusOutlined, UploadOutlined, AppstoreOutlined, UnorderedListOutlined, MoreOutlined, FileAddOutlined } from '@ant-design/icons';
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
  isMobile?: boolean;
  onGoUp: () => void;
  onNavigate: (path: string) => void;
  onRefresh: () => void;
  onCreateDir: () => void;
  onCreateFile: () => void;
  onUploadFile: () => void;
  onUploadDirectory: () => void;
  onSetViewMode: (mode: ViewMode) => void;
  onSortChange: (sortBy: string, sortOrder: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  path,
  loading,
  viewMode,
  sortBy,
  sortOrder,
  isMobile = false,
  onGoUp,
  onNavigate,
  onRefresh,
  onCreateDir,
  onCreateFile,
  onUploadFile,
  onUploadDirectory,
  onSetViewMode,
  onSortChange,
}) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const [editingPath, setEditingPath] = useState(false);
  const [pathInputValue, setPathInputValue] = useState('');
  const clickTimerRef = useRef<number | null>(null);
  const pathEditorHeight = token.fontSizeSM * token.lineHeight + token.paddingXXS * 2;

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
  };

  const handlePathCancel = () => {
    setEditingPath(false);
    setPathInputValue('');
  };

  const renderBreadcrumb = () => {
    if (editingPath) {
      return (
        <Input
          size="small"
          value={pathInputValue}
          onChange={(e) => setPathInputValue(e.target.value)}
          onPressEnter={handlePathSubmit}
          onBlur={handlePathCancel}
          onKeyDown={(e) => e.key === 'Escape' && handlePathCancel()}
          autoFocus
          style={{ flex: 1, height: pathEditorHeight, boxSizing: 'border-box' }}
        />
      );
    }

    const breadcrumbItems = [
      { key: 'root', title: <span style={{ cursor: 'pointer' }} onClick={() => scheduleNavigate('/')}>{t('Home')}</span> },
      ...path.split('/').filter(Boolean).map((segment, index, arr) => {
        const segmentPath = '/' + arr.slice(0, index + 1).join('/');
        return {
          key: segmentPath,
          title: <span style={{ cursor: 'pointer' }} onClick={() => scheduleNavigate(segmentPath)}>{segment}</span>,
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
        <Breadcrumb items={breadcrumbItems} separator="/" style={{ fontSize: token.fontSizeSM }} />
      </div>
    );
  };

  const mobileMoreItems = [
    {
      key: 'new-file',
      label: t('New File'),
      icon: <FileAddOutlined />,
      onClick: onCreateFile,
    },
    {
      key: 'upload-folder',
      label: t('Upload Folder'),
      icon: <UploadOutlined />,
      onClick: onUploadDirectory,
    },
    {
      key: 'sort',
      label: t('Sort By') + `: ${t(sortBy === 'mtime' ? 'Modified Time' : sortBy === 'size' ? 'Size' : 'Name')}`,
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
    return (
      <Flex align="center" gap={6} style={{ padding: '10px 12px', borderBottom: `1px solid ${token.colorBorderSecondary}`, minWidth: 0 }}>
        <Button size="small" icon={<ArrowUpOutlined />} onClick={onGoUp} disabled={path === '/'} />
        {renderBreadcrumb()}
        <Space size={4} style={{ flexShrink: 0 }}>
          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading} aria-label={t('Refresh')} />
          <Button size="small" icon={<PlusOutlined />} onClick={onCreateDir} aria-label={t('New Folder')} />
          <Button size="small" icon={<UploadOutlined />} onClick={onUploadFile} aria-label={t('Upload Files')} />
          <Dropdown menu={{ items: mobileMoreItems }}>
            <Button size="small" icon={<MoreOutlined />} aria-label={t('More')} />
          </Dropdown>
        </Space>
      </Flex>
    );
  }

  return (
    <Flex vertical gap={12} style={{ padding: '10px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}` }}>
      <Flex align="center" gap={8} style={{ minWidth: 0 }}>
        <Button size="small" icon={<ArrowUpOutlined />} onClick={onGoUp} disabled={path === '/'} />
        <Typography.Text strong>{t('File Manager')}</Typography.Text>
        <Divider type="vertical" />
        {renderBreadcrumb()}
      </Flex>

      <Flex align="center" justify="space-between" gap={8} style={{ flexWrap: 'wrap' }}>
        <Space size={8} wrap>
          <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading} aria-label={t('Refresh')}>
            {t('Refresh')}
          </Button>
          <Button size="small" icon={<PlusOutlined />} onClick={onCreateDir} aria-label={t('New Folder')}>
            {t('New Folder')}
          </Button>
          <Dropdown.Button
            size="small"
            icon={<UploadOutlined />}
            onClick={onUploadFile}
            menu={uploadMenu}
          >
            {t('Upload')}
          </Dropdown.Button>
        </Space>

        <Space size={8} wrap>
          <Select
            size="small"
            value={sortBy}
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
            icon={sortOrder === 'asc' ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            onClick={() => onSortChange(sortBy, sortOrder === 'asc' ? 'desc' : 'asc')}
          />
          <Segmented
            size="small"
            value={viewMode}
            onChange={(value) => onSetViewMode(value as ViewMode)}
            options={[
              { label: <Tooltip title={t('Grid')}><AppstoreOutlined /></Tooltip>, value: 'grid' },
              { label: <Tooltip title={t('List')}><UnorderedListOutlined /></Tooltip>, value: 'list' },
            ]}
          />
        </Space>
      </Flex>
    </Flex>
  );
};
