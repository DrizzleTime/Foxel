import React from 'react';
import { Empty, Flex, Spin, Tag, Typography, theme } from 'antd';
import { useI18n } from '../../../i18n';
import type { VfsEntry } from '../../../api/client';
import type { ViewMode } from '../types';
import type { SearchDisplayItem, SearchMode } from '../hooks/useFileSearch';

interface SearchResultsViewProps {
  viewMode: ViewMode;
  loading: boolean;
  mode: SearchMode;
  query: string;
  items: SearchDisplayItem[];
  selectedPaths: string[];
  entrySnapshot: Record<string, VfsEntry>;
  onClearSearch: () => void;
  onSelect: (fullPath: string, additive: boolean) => void;
  onOpen: (fullPath: string) => void;
  onContextMenu: (e: React.MouseEvent, fullPath: string) => void;
}

export const SearchResultsView: React.FC<SearchResultsViewProps> = ({
  viewMode,
  loading,
  mode,
  query,
  items,
  selectedPaths,
  entrySnapshot,
  onClearSearch,
  onSelect,
  onOpen,
  onContextMenu,
}) => {
  const { token } = theme.useToken();
  const { t } = useI18n();

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

  const normalizeSnippet = (rawSnippet: string | undefined, name: string, fullPath: string) => {
    const snippet = (rawSnippet || '').trim();
    if (!snippet) return '';
    if (snippet === name) return '';
    if (snippet === fullPath) return '';
    if (snippet === fullPath.replace(/^\/+/, '')) return '';
    return snippet;
  };

  return (
    <div style={{ padding: 16 }}>
      <Flex align="center" justify="space-between" style={{ marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <Flex align="center" style={{ gap: 8, flexWrap: 'wrap' }}>
          <Typography.Text strong>{t('Search Results')}</Typography.Text>
          <Tag color={mode === 'filename' ? 'green' : 'blue'}>
            {mode === 'filename' ? t('Name Search') : t('Smart Search')}
          </Tag>
          <Tag closable onClose={(ev) => { ev.preventDefault(); onClearSearch(); }}>
            {query}
          </Tag>
        </Flex>
      </Flex>

      {loading ? (
        <Flex align="center" justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : items.length === 0 ? (
        <Flex align="center" justify="center" style={{ padding: 48 }}>
          <Empty description={t('No files found')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </Flex>
      ) : viewMode === 'grid' ? (
        <div
          className="fx-grid"
          style={{ padding: 0, gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}
        >
          {items.map(({ item, fullPath, dir, name }) => {
            const selected = selectedPaths.includes(fullPath);
            const scoreText = Number.isFinite(item.score) ? item.score.toFixed(2) : '-';
            const isDir = Boolean(entrySnapshot[fullPath]?.is_dir);

            return (
              <div
                key={fullPath}
                className={['fx-grid-item', selected ? 'selected' : '', 'file'].join(' ')}
                onClick={(ev) => onSelect(fullPath, ev.ctrlKey || ev.metaKey)}
                onDoubleClick={() => onOpen(fullPath)}
                onContextMenu={(ev) => onContextMenu(ev, fullPath)}
                style={{ userSelect: 'none' }}
              >
                <div className="thumb" style={{ background: 'var(--ant-color-bg-container, #fff)' }}>
                  <span className="badge score-badge">{scoreText}</span>
                  {isDir
                    ? <Typography.Text style={{ fontSize: 32, color: token.colorPrimary }}>📁</Typography.Text>
                    : <Typography.Text style={{ fontSize: 32, color: token.colorTextTertiary }}>📄</Typography.Text>}
                </div>
                <div className="name ellipsis">{name}</div>
                <Typography.Text type="secondary" className="ellipsis" style={{ fontSize: 12 }}>
                  {dir}
                </Typography.Text>
              </div>
            );
          })}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(({ item, fullPath, name }) => {
            const selected = selectedPaths.includes(fullPath);
            const retrieval = item.metadata?.retrieval_source || item.source_type;
            const scoreText = Number.isFinite(item.score) ? item.score.toFixed(2) : '-';
            const snippet = normalizeSnippet(item.snippet, name, fullPath);

            return (
              <div
                key={fullPath}
                className={selected ? 'row-selected' : ''}
                onClick={(ev) => onSelect(fullPath, ev.ctrlKey || ev.metaKey)}
                onDoubleClick={() => onOpen(fullPath)}
                onContextMenu={(ev) => onContextMenu(ev, fullPath)}
                style={{
                  padding: '10px 12px',
                  borderRadius: token.borderRadius,
                  background: token.colorFillTertiary,
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
              >
                <Flex vertical style={{ gap: 6 }}>
                  <Typography.Text strong className="ellipsis">
                    {name}
                  </Typography.Text>
                  <Typography.Text type="secondary" className="ellipsis" style={{ fontSize: 12 }}>
                    {fullPath}
                  </Typography.Text>
                  {snippet ? (
                    <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0 }}>
                      {snippet}
                    </Typography.Paragraph>
                  ) : null}
                  <Flex align="center" style={{ gap: 8, flexWrap: 'wrap' }}>
                    {retrieval ? (
                      <Tag color={sourceColor(retrieval)} style={{ marginRight: 0 }}>
                        {renderSourceLabel(retrieval)}
                      </Tag>
                    ) : null}
                    <Tag
                      style={{
                        marginRight: 0,
                        background: token.colorBgContainer,
                        borderColor: token.colorBorderSecondary,
                        color: token.colorText,
                      }}
                    >
                      {scoreText}
                    </Tag>
                  </Flex>
                </Flex>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
