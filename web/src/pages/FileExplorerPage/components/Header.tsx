import React, { useState } from 'react';
import { Flex, Typography, Divider, Button, Space, Tooltip, Segmented, Breadcrumb, Input, theme, Dropdown } from 'antd';
import { ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined, PlusOutlined, UploadOutlined, AppstoreOutlined, UnorderedListOutlined } from '@ant-design/icons';
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
  onGoUp: () => void;
  onNavigate: (path: string) => void;
  onRefresh: () => void;
  onCreateDir: () => void;
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
  onGoUp,
  onNavigate,
  onRefresh,
  onCreateDir,
  onUploadFile,
  onUploadDirectory,
  onSetViewMode,
  onSortChange,
}) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const [editingPath, setEditingPath] = useState(false);
  const [pathInputValue, setPathInputValue] = useState('');
  const pathEditorHeight = token.fontSizeSM * token.lineHeight + token.paddingXXS * 2;

  const handlePathEdit = () => {
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
      { key: 'root', title: <span style={{ cursor: 'pointer' }} onClick={() => onNavigate('/')}>{t('Home')}</span> },
      ...path.split('/').filter(Boolean).map((segment, index, arr) => {
        const segmentPath = '/' + arr.slice(0, index + 1).join('/');
        return {
          key: segmentPath,
          title: <span style={{ cursor: 'pointer' }} onClick={() => onNavigate(segmentPath)}>{segment}</span>
        };
      })
    ];

    return (
      <div
        style={{
          cursor: 'pointer',
          padding: `${token.paddingXXS}px ${token.paddingXS}px`,
          borderRadius: token.borderRadius,
          transition: 'background-color 0.2s',
          flex: 1,
          overflow: 'hidden',
          height: pathEditorHeight,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center'
        }}
        onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = token.colorFillTertiary; }}
        onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'transparent'; }}
        onClick={handlePathEdit}
      >
        <Breadcrumb items={breadcrumbItems} separator="/" style={{ fontSize: token.fontSizeSM }} />
      </div>
    );
  };

  return (
    <Flex align="center" justify="space-between" style={{ padding: '10px 16px', borderBottom: `1px solid ${token.colorBorderSecondary}`, gap: 12 }}>
      <Flex align="center" gap={8} style={{ flexWrap: 'wrap', flex: 1, overflow: 'hidden' }}>
        <Button size="small" icon={<ArrowUpOutlined />} onClick={onGoUp} disabled={path === '/'} />
        <Typography.Text strong>{t('File Manager')}</Typography.Text>
        <Divider type="vertical" />
        {renderBreadcrumb()}
      </Flex>
      <Space size={8} wrap>
        <Button size="small" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>{t('Refresh')}</Button>
        <Button size="small" icon={<PlusOutlined />} onClick={onCreateDir}>{t('New Folder')}</Button>
        <Dropdown.Button
          size="small"
          icon={<UploadOutlined />}
          onClick={onUploadFile}
          menu={{
            items: [
              { key: 'file', label: t('Upload Files') },
              { key: 'folder', label: t('Upload Folder') },
            ],
            onClick: ({ key }) => {
              if (key === 'folder') {
                onUploadDirectory();
              } else {
                onUploadFile();
              }
            },
          }}
        >
          {t('Upload')}
        </Dropdown.Button>
        <Select
          size="small"
          value={sortBy}
          onChange={(val) => onSortChange(val, sortOrder)}
          style={{ width: 80 }}
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
          onChange={value => onSetViewMode(value as ViewMode)}
          options={[
            { label: <Tooltip title={t('Grid')}><AppstoreOutlined /></Tooltip>, value: 'grid' },
            { label: <Tooltip title={t('List')}><UnorderedListOutlined /></Tooltip>, value: 'list' }
          ]}
        />
      </Space>
    </Flex>
  );
};
