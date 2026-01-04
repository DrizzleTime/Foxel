/**
 * 视频库应用组件
 */
import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  Flex,
  Input,
  Button,
  Empty,
  Skeleton,
  Tag,
  Typography,
  Segmented,
  Space,
  message,
  Drawer,
  Image,
  theme,
} from 'antd';
import {
  SearchOutlined,
  ReloadOutlined,
  PlayCircleOutlined,
  VideoCameraOutlined,
} from '@ant-design/icons';
import type { AppContext } from './foxel-types';
import type { LibraryItem, LibraryItemDetail } from './type';
import { tmdbImage } from './utils';
import { fetchLibrary, fetchLibraryItem } from './api';
import { t as i18nT, useI18n } from './i18n';

export const VideoLibraryApp: React.FC<AppContext> = () => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<'all' | 'movie' | 'tv'>('all');
  const [items, setItems] = useState<LibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selected, setSelected] = useState<LibraryItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<LibraryItemDetail | null>(null);

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchLibrary();
      setItems(list || []);
    } catch (err: any) {
      setItems([]);
      message.error(i18nT(err?.message || 'Load failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLibrary();
  }, [loadLibrary]);

  const stats = useMemo(() => {
    let tv = 0;
    let movie = 0;
    items.forEach((it) => {
      if (it.type === 'tv') tv += 1;
      if (it.type === 'movie') movie += 1;
    });
    return { total: items.length, tv, movie };
  }, [items]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return items.filter((v) => {
      if (filter !== 'all' && v.type !== filter) return false;
      if (!s) return true;
      const haystack = `${v.title || ''} ${v.overview || ''} ${(v.genres || []).join(' ')}`.toLowerCase();
      return haystack.includes(s);
    });
  }, [filter, items, q]);

  const fetchDetail = useCallback(async (item: LibraryItem) => {
    setDetailLoading(true);
    setDetail(null);
    try {
      const payload = await fetchLibraryItem(item.id);
      setDetail(payload);
    } catch (err: any) {
      setDetail(null);
      message.error(i18nT(err?.message || 'Load failed'));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const openDetail = (item: LibraryItem) => {
    setSelected(item);
    setDetailOpen(true);
    fetchDetail(item);
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setSelected(null);
    setDetail(null);
  };

  const renderCover = (item: LibraryItem) => {
    const label = item.type === 'tv' ? t('TV') : t('Movie');
    const coverUrl = tmdbImage(item.poster_path, 'w342') || tmdbImage(item.backdrop_path, 'w780');

    return (
      <div
        style={{
          position: 'relative',
          width: '100%',
          aspectRatio: '2 / 3',
          background: 'linear-gradient(135deg, #0b1020 0%, #22314a 55%, #2b3b5c 100%)',
          overflow: 'hidden',
        }}
      >
        {coverUrl ? (
          <Image
            src={coverUrl}
            alt={item.title || label}
            preview={false}
            wrapperStyle={{ width: '100%', height: '100%', display: 'block' }}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            fallback="/logo.svg"
          />
        ) : (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'rgba(255,255,255,0.7)',
            }}
          >
            <VideoCameraOutlined style={{ fontSize: 28 }} />
          </div>
        )}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(180deg, rgba(0,0,0,0.48) 0%, rgba(0,0,0,0.12) 40%, rgba(0,0,0,0.45) 100%)',
            pointerEvents: 'none',
          }}
        />
        <div
          style={{
            position: 'absolute',
            top: 10,
            left: 10,
            right: 10,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 8,
            pointerEvents: 'none',
          }}
        >
          <Tag color={item.type === 'tv' ? 'geekblue' : 'gold'} style={{ marginInlineEnd: 0 }}>
            {label}
          </Tag>
          <VideoCameraOutlined style={{ fontSize: 18, opacity: 0.9, color: 'rgba(255,255,255,0.9)' }} />
        </div>
        <div
          style={{
            position: 'absolute',
            left: 10,
            bottom: 10,
            width: 36,
            height: 36,
            borderRadius: 999,
            background: 'rgba(2,6,23,0.55)',
            border: '1px solid rgba(255,255,255,0.22)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'rgba(255,255,255,0.92)',
            boxShadow: token.boxShadowTertiary,
            pointerEvents: 'none',
          }}
        >
          <PlayCircleOutlined style={{ fontSize: 20 }} />
        </div>
      </div>
    );
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgLayout }}>
      {/* Header */}
      <div
        style={{
          padding: 14,
          borderRadius: 12,
          background: token.colorBgContainer,
          border: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Flex align="center" justify="space-between" gap={12} wrap>
          <div style={{ minWidth: 240 }}>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {t('Video Library')}
            </Typography.Title>
            <Typography.Text type="secondary">
              {t('Total: {total} · Movies: {movies} · TV Shows: {tvShows}', { total: stats.total, movies: stats.movie, tvShows: stats.tv })}
            </Typography.Text>
          </div>
          <Space size={10} wrap>
            <Segmented
              value={filter}
              onChange={(v) => setFilter(v as 'all' | 'movie' | 'tv')}
              options={[
                { value: 'all', label: t('All') },
                { value: 'movie', label: t('Movies') },
                { value: 'tv', label: t('TV Shows') },
              ]}
            />
            <Input
              allowClear
              value={q}
              onChange={(e) => setQ(e.target.value)}
              prefix={<SearchOutlined />}
              placeholder={t('Search')}
              style={{ width: 260 }}
            />
            <Button icon={<ReloadOutlined />} onClick={loadLibrary} loading={loading}>
              {t('Refresh')}
            </Button>
          </Space>
        </Flex>
      </div>

      {/* Content */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '12px 2px' }}>
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 }}>
            {Array.from({ length: 10 }).map((_, idx) => (
              <Card
                key={idx}
                size="small"
                style={{ borderRadius: 12, overflow: 'hidden' }}
                cover={
                  <div style={{ width: '100%', aspectRatio: '2 / 3' }}>
                    <Skeleton.Image active style={{ width: '100%', height: '100%' }} />
                  </div>
                }
              >
                <Skeleton active paragraph={{ rows: 2 }} />
              </Card>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <Empty description={t('No data')} style={{ marginTop: 48 }} />
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 }}>
            {filtered.map((v) => (
              <Card
                key={v.id}
                hoverable
                size="small"
                styles={{ body: { padding: 10 } }}
                style={{
                  borderRadius: 12,
                  overflow: 'hidden',
                  boxShadow: token.boxShadowTertiary,
                  border: `1px solid ${token.colorBorderSecondary}`,
                }}
                cover={renderCover(v)}
                onClick={() => openDetail(v)}
              >
                <Typography.Text strong ellipsis style={{ display: 'block' }}>
                  {v.title || '--'}
                </Typography.Text>
                <div style={{ marginTop: 6, display: 'flex', gap: 8, color: token.colorTextTertiary, fontSize: 12 }}>
                  <span>{v.year || '--'}</span>
                  {v.type === 'tv' && (
                    <>
                      <span>·</span>
                      <span>{t('{count} episodes', { count: v.episodes_count || 0 })}</span>
                    </>
                  )}
                </div>
                <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(v.genres || []).slice(0, 3).map((tag) => (
                    <Tag key={tag} style={{ marginInlineEnd: 0 }}>
                      {tag}
                    </Tag>
                  ))}
                  {(v.genres || []).length > 3 && (
                    <Tag style={{ marginInlineEnd: 0 }}>{`+${(v.genres || []).length - 3}`}</Tag>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Detail Drawer */}
      <Drawer
        title={selected?.title || t('Details')}
        open={detailOpen}
        onClose={closeDetail}
        width="100%"
        destroyOnClose
        styles={{ body: { padding: 0 } }}
      >
        {detailLoading ? (
          <div style={{ padding: 16 }}>
            <Skeleton active paragraph={{ rows: 10 }} />
          </div>
        ) : !detail ? (
          <Empty description={t('No data')} style={{ marginTop: 48 }} />
        ) : (
          <div style={{ padding: 16 }}>
            <Typography.Title level={4}>{detail.tmdb?.detail?.title || detail.tmdb?.detail?.name || '--'}</Typography.Title>
            <Typography.Paragraph>{detail.tmdb?.detail?.overview || t('No overview')}</Typography.Paragraph>
          </div>
        )}
      </Drawer>
    </div>
  );
};
