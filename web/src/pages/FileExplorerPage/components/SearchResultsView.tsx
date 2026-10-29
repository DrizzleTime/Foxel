import React from 'react';
import { Alert, Empty, Flex, Spin, Tag, Typography, theme, Button } from 'antd';
import { MoreOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import type { VfsEntry } from '../../../api/client';
import type { ViewMode } from '../types';
import type { SearchDisplayItem } from '../hooks/useFileSearch';
import type { SearchWarning } from '../../../api/vfs';
import { formatIndexLocation } from './indexLocation';
import { handleFileItemKeyDown } from './fileItemKeyboard';
import { FileOutlined, FolderOutlined } from '@ant-design/icons';

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return '-';
  return score < 0.1 ? score.toFixed(3) : score.toFixed(2);
}

function resultChannels(metadata?: Record<string, unknown>): Array<'bm25' | 'vector'> {
  const raw = metadata?.channels;
  const values = Array.isArray(raw) ? raw : [];
  const found = values.filter((value): value is 'bm25' | 'vector' => value === 'bm25' || value === 'vector');
  if (found.length) {
    return (['bm25', 'vector'] as const).filter((channel) => found.includes(channel));
  }
  const source = String(metadata?.retrieval_source || '');
  if (source === 'hybrid') return ['bm25', 'vector'];
  if (source === 'bm25' || source === 'filename') return ['bm25'];
  if (source === 'vector') return ['vector'];
  return [];
}

interface SearchResultsViewProps {
  viewMode: ViewMode;
  loading: boolean;
  query: string;
  items: SearchDisplayItem[];
  warnings: SearchWarning[];
  selectedPaths: string[];
  entrySnapshot: Record<string, VfsEntry>;
  mobile?: boolean;
  onClearSearch: () => void;
  onSelect: (fullPath: string, additive: boolean) => void;
  onOpen: (fullPath: string) => void;
  onContextMenu: (e: React.MouseEvent, fullPath: string) => void;
  onOpenMenu?: (fullPath: string, anchor: HTMLElement) => void;
}

export const SearchResultsView: React.FC<SearchResultsViewProps> = ({
  viewMode,
  loading,
  query,
  items,
  warnings,
  selectedPaths,
  entrySnapshot,
  mobile = false,
  onClearSearch,
  onSelect,
  onOpen,
  onContextMenu,
  onOpenMenu,
}) => {
  const { token } = theme.useToken();
  const { t } = useI18n();

  const channelTags = (metadata?: Record<string, unknown>) => (
    resultChannels(metadata).map((channel) => (
      <Tag key={channel} color={channel === 'bm25' ? 'green' : 'blue'} style={{ marginRight: 0 }}>
        {channel === 'bm25' ? t('Keyword') : t('Semantic')}
      </Tag>
    ))
  );

  const normalizeSnippet = (rawSnippet: string | undefined, name: string, fullPath: string) => {
    const snippet = (rawSnippet || '').trim();
    if (!snippet) return '';
    if (snippet === name) return '';
    if (snippet === fullPath) return '';
    if (snippet === fullPath.replace(/^\/+/, '')) return '';
    return snippet;
  };

  return (
    <div style={{ padding: mobile ? 12 : 16 }}>
      <Flex align="center" justify="space-between" style={{ marginBottom: 12, gap: 12, flexWrap: 'wrap' }}>
        <Flex align="center" style={{ gap: 8, flexWrap: 'wrap' }}>
          <Typography.Text strong>{t('Search Results')}</Typography.Text>
          <Tag closable onClose={(ev) => { ev.preventDefault(); onClearSearch(); }}>
            {query}
          </Tag>
        </Flex>
      </Flex>

      {warnings.map((warning) => (
        <Alert
          key={warning.source}
          type="warning"
          showIcon
          title={warning.source === 'vector' ? t('Semantic search failed') : t('Keyword search failed')}
          description={warning.message}
          style={{ marginBottom: 12, overflowWrap: 'anywhere' }}
        />
      ))}

      {loading ? (
        <Flex align="center" justify="center" style={{ padding: 48 }}>
          <Spin />
        </Flex>
      ) : items.length === 0 ? (
        <Flex align="center" justify="center" style={{ padding: 48 }}>
          <Empty description={t('No files found')} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        </Flex>
      ) : viewMode === 'grid' ? (
        <div data-file-items className="fx-grid" style={{ padding: 0, gridTemplateColumns: mobile ? 'repeat(auto-fill, minmax(160px, 1fr))' : 'repeat(auto-fill, minmax(220px, 1fr))' }}>
          {items.map(({ item, fullPath, dir, name }) => {
            const selected = selectedPaths.includes(fullPath);
            const scoreText = formatScore(item.score);
            const isDir = Boolean(entrySnapshot[fullPath]?.is_dir);
            const locationText = formatIndexLocation(item.metadata, t);

            return (
              <div
                key={fullPath}
                className={['fx-grid-item', selected ? 'selected' : '', 'file'].join(' ')}
                onClick={(ev) => {
                  if (mobile) {
                    onOpen(fullPath);
                    return;
                  }
                  onSelect(fullPath, ev.ctrlKey || ev.metaKey);
                }}
                onDoubleClick={() => {
                  if (!mobile) onOpen(fullPath);
                }}
                onContextMenu={(ev) => {
                  if (!mobile) onContextMenu(ev, fullPath);
                }}
                style={{ userSelect: 'none' }}
              >
                {mobile && onOpenMenu && (
                  <Button
                    className="fx-file-more-button"
                    size="small"
                    type="text"
                    icon={<MoreOutlined />}
                    aria-label={t('More actions for {name}', { name })}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenMenu(fullPath, e.currentTarget);
                    }}
                    style={{ position: 'absolute', top: 4, right: 4, zIndex: 2 }}
                  />
                )}
                <div
                  className="fx-file-card-action"
                  data-file-item
                  role="button"
                  tabIndex={0}
                  aria-label={name}
                  aria-pressed={selected}
                  onKeyDown={(event) => handleFileItemKeyDown(event, {
                    open: () => onOpen(fullPath),
                    select: () => mobile ? onOpen(fullPath) : onSelect(fullPath, true),
                    menu: onOpenMenu ? () => onOpenMenu(fullPath, event.currentTarget) : undefined,
                  })}
                >
                  <div className="thumb" style={{ background: 'var(--ant-color-bg-container, #fff)' }}>
                    <span className="badge score-badge">{scoreText}</span>
                    {isDir ? <FolderOutlined style={{ fontSize: 32, color: token.colorText }} /> : <FileOutlined style={{ fontSize: 32, color: token.colorTextTertiary }} />}
                  </div>
                  <div className="name ellipsis">{name}</div>
                  <Typography.Text type="secondary" className="ellipsis" style={{ fontSize: 12 }}>
                    {dir}
                  </Typography.Text>
                  <Flex align="center" style={{ gap: 4, flexWrap: 'wrap' }}>
                    {channelTags(item.metadata)}
                  </Flex>
                  {locationText ? (
                    <Typography.Text type="secondary" className="ellipsis" style={{ fontSize: 12 }}>
                      {locationText}
                    </Typography.Text>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div data-file-items style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {items.map(({ item, fullPath, name }) => {
            const selected = selectedPaths.includes(fullPath);
            const scoreText = formatScore(item.score);
            const snippet = normalizeSnippet(item.snippet, name, fullPath);
            const locationText = formatIndexLocation(item.metadata, t);

            return (
              <div
                key={fullPath}
                className={selected ? 'row-selected' : ''}
                onClick={(ev) => {
                  if (mobile) {
                    onOpen(fullPath);
                    return;
                  }
                  onSelect(fullPath, ev.ctrlKey || ev.metaKey);
                }}
                onDoubleClick={() => {
                  if (!mobile) onOpen(fullPath);
                }}
                onContextMenu={(ev) => {
                  if (!mobile) onContextMenu(ev, fullPath);
                }}
                style={{
                  padding: '10px 12px',
                  borderRadius: token.borderRadius,
                  background: token.colorFillTertiary,
                  cursor: 'pointer',
                  userSelect: 'none',
                  position: 'relative',
                }}
              >
                {mobile && onOpenMenu && (
                  <Button
                    className="fx-file-more-button"
                    size="small"
                    type="text"
                    icon={<MoreOutlined />}
                    aria-label={t('More actions for {name}', { name })}
                    onClick={(e) => {
                      e.stopPropagation();
                      onOpenMenu(fullPath, e.currentTarget);
                    }}
                    style={{ position: 'absolute', top: 6, right: 6 }}
                  />
                )}
                <Flex
                  vertical
                  data-file-item
                  role="button"
                  tabIndex={0}
                  aria-label={name}
                  aria-pressed={selected}
                  onKeyDown={(event) => handleFileItemKeyDown(event, {
                    open: () => onOpen(fullPath),
                    select: () => mobile ? onOpen(fullPath) : onSelect(fullPath, true),
                    menu: onOpenMenu ? () => onOpenMenu(fullPath, event.currentTarget) : undefined,
                  })}
                  style={{ gap: 6, paddingRight: mobile ? 44 : 0 }}
                >
                  <Typography.Text strong className="ellipsis">{name}</Typography.Text>
                  <Typography.Text type="secondary" className="ellipsis" style={{ fontSize: 12 }}>{fullPath}</Typography.Text>
                  {locationText ? <Typography.Text type="secondary" style={{ fontSize: 12 }}>{locationText}</Typography.Text> : null}
                  {snippet ? <Typography.Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0 }}>{snippet}</Typography.Paragraph> : null}
                  <Flex align="center" style={{ gap: 8, flexWrap: 'wrap' }}>
                    {channelTags(item.metadata)}
                    <Tag style={{ marginRight: 0, background: token.colorBgContainer, borderColor: token.colorBorderSecondary, color: token.colorText }}>{scoreText}</Tag>
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
