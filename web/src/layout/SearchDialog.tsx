import { Modal, Input, List, Divider, Spin, Space, Tag, Typography, Empty, Flex, Segmented, Pagination } from 'antd';
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import React, { useRef, useState } from 'react';
import { vfsApi, type SearchResultItem } from '../api/vfs';
import { useI18n } from '../i18n';
import { useNavigate } from 'react-router';

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
    } catch (e) {
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
    if (search.trim()) {
      void performSearch({ mode: nextMode, page: nextMode === 'filename' ? 1 : undefined });
    } else {
      setResults([]);
      setSearched(false);
    }
  };

  const handleClose = () => {
    setSearch('');
    setResults([]);
    setSearched(false);
    setSearchMode('vector');
    setPage(1);
    setHasMore(false);
    requestIdRef.current = 0;
    setLoading(false);
    onClose();
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
                        <List.Item style={{ padding: '10px 12px', borderRadius: 6, background: '#fafafa', marginBottom: 8 }}>
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
    </Modal>
  );
};

export default SearchDialog;
