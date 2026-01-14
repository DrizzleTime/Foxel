import { memo, useEffect, useMemo, useState } from 'react';
import { Modal, List, Typography, theme, Flex, Button, Empty, message, Divider, Spin } from 'antd';
import ReactMarkdown from 'react-markdown';
import { format } from 'date-fns';
import { noticesApi, type NoticeItem } from '../api/notices';
import { useI18n } from '../i18n';

export interface NoticesModalProps {
  open: boolean;
  version: string;
  onClose: () => void;
}

const NoticesModal = memo(function NoticesModal({ open, version, onClose }: NoticesModalProps) {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const [items, setItems] = useState<NoticeItem[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const selected = useMemo(() => items.find(i => i.id === selectedId) ?? null, [items, selectedId]);
  const hasMore = items.length < total;

  const loadPage = async (targetPage: number, mode: 'replace' | 'append') => {
    if (mode === 'replace') setLoading(true);
    else setLoadingMore(true);
    try {
      const resp = await noticesApi.list({ version, page: targetPage });
      setPage(resp.page ?? targetPage);
      setTotal(resp.total ?? 0);
      setItems(prev => mode === 'replace' ? resp.items : [...prev, ...resp.items]);
      if (mode === 'replace') {
        setSelectedId(resp.items[0]?.id ?? null);
      } else {
        setSelectedId(prev => prev ?? resp.items[0]?.id ?? null);
      }
    } catch (e) {
      if (e instanceof Error) {
        message.error(e.message || t('Error'));
      }
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    if (!open) return;
    setItems([]);
    setPage(1);
    setTotal(0);
    setSelectedId(null);
    loadPage(1, 'replace');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, version]);

  const formatTime = (ts: number) => {
    try {
      return format(new Date(ts), 'yyyy-MM-dd HH:mm');
    } catch {
      return '';
    }
  };

  return (
    <Modal
      title={t('Notices')}
      open={open}
      onCancel={onClose}
      footer={null}
      width={980}
      styles={{
        body: {
          padding: 0,
          height: '70vh',
          overflow: 'hidden',
        },
      }}
    >
      <Flex style={{ height: '70vh', minHeight: 0 }}>
        <div style={{
          width: 320,
          minWidth: 280,
          borderRight: `1px solid ${token.colorBorderSecondary}`,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
        }}>
          <div style={{
            padding: '10px 12px',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 12,
          }}>
            <Typography.Text type="secondary">{t('Total')}: {total}</Typography.Text>
            <Typography.Text type="secondary">{items.length}/{total}</Typography.Text>
          </div>
          <List
            size="small"
            loading={loading && items.length === 0}
            dataSource={items}
            style={{ flex: 1, minHeight: 0, overflow: 'auto' }}
            renderItem={(item) => {
              const isSelected = item.id === selectedId;
              return (
                <List.Item
                  onClick={() => setSelectedId(item.id)}
                  style={{
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(22,119,255,0.08)' : undefined,
                    borderInlineStart: isSelected ? `3px solid ${token.colorPrimary}` : '3px solid transparent',
                    paddingInlineStart: 10,
                  }}
                >
                  <List.Item.Meta
                    title={<Typography.Text strong={isSelected}>{item.title}</Typography.Text>}
                    description={<Typography.Text type="secondary">{formatTime(item.createdAt)}</Typography.Text>}
                  />
                </List.Item>
              );
            }}
          />
          <div style={{
            padding: 12,
            borderTop: `1px solid ${token.colorBorderSecondary}`,
          }}>
            <Button
              block
              loading={loadingMore}
              disabled={!hasMore}
              onClick={() => loadPage(page + 1, 'append')}
            >
              {t('Load more')}
            </Button>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, padding: 16, overflow: 'auto' }}>
          {selected ? (
            <>
              <Typography.Title level={4} style={{ marginTop: 0, marginBottom: 6 }}>
                {selected.title}
              </Typography.Title>
              <Typography.Text type="secondary">{formatTime(selected.createdAt)}</Typography.Text>
              <Divider style={{ margin: '12px 0' }} />
              {selected.contentMd?.trim() ? (
                <div style={{ color: token.colorText, lineHeight: 1.7 }}>
                  <ReactMarkdown
                    components={{
                      a: ({ ...props }) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                      ul: ({ ...props }) => <ul style={{ paddingLeft: 20, marginBottom: 12 }} {...props} />,
                      li: ({ ...props }) => <li style={{ marginBottom: 6 }} {...props} />,
                      p: ({ ...props }) => <p style={{ marginBottom: 12 }} {...props} />,
                    }}
                  >
                    {selected.contentMd}
                  </ReactMarkdown>
                </div>
              ) : (
                <Empty description={t('No content')} />
              )}
            </>
          ) : (
            loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
                <Spin />
              </div>
            ) : (
              <Empty description={t('No notices')} />
            )
          )}
        </div>
      </Flex>
    </Modal>
  );
});

export default NoticesModal;

