import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Avatar,
  Button,
  Card,
  Collapse,
  Descriptions,
  Divider,
  Drawer,
  Empty,
  Flex,
  Image,
  Input,
  List,
  Segmented,
  Skeleton,
  Space,
  Tabs,
  Tag,
  Typography,
  message,
  theme,
} from 'antd';
import { PlayCircleOutlined, ReloadOutlined, SearchOutlined, VideoCameraOutlined } from '@ant-design/icons';
import type { AppOpenComponentProps } from '../types';
import { videoLibraryApi, type VideoLibraryItem } from '../../api/videoLibrary';
import { useI18n } from '../../i18n';
import { ensureAppsLoaded, getAppByKey } from '../registry';
import { useAppWindows } from '../../contexts/AppWindowsContext';
import type { VfsEntry } from '../../api/client';

type LibraryFilter = 'all' | 'tv' | 'movie';

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/';

function tmdbImage(path: string | null | undefined, size: string) {
  if (!path) return undefined;
  return `${TMDB_IMAGE_BASE}${size}${path}`;
}

function splitAbsolutePath(fullPath: string): { dir: string; name: string } | null {
  const normalized = fullPath.replace(/\/+$/, '');
  const idx = normalized.lastIndexOf('/');
  if (idx < 0) return null;
  const dir = idx === 0 ? '/' : normalized.slice(0, idx);
  const name = normalized.slice(idx + 1);
  if (!name) return null;
  return { dir, name };
}

export const VideoLibraryApp: React.FC<AppOpenComponentProps> = () => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const { openWithApp } = useAppWindows();
  const [q, setQ] = useState('');
  const [filter, setFilter] = useState<LibraryFilter>('all');
  const [items, setItems] = useState<VideoLibraryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selected, setSelected] = useState<VideoLibraryItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<any | null>(null);

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    try {
      const list = await videoLibraryApi.list();
      setItems(list);
    } catch (err: any) {
      setItems([]);
      const msg = err instanceof Error ? err.message : t('Load failed');
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [t]);

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

  const playByPath = useCallback(async (fullPath: string) => {
    const splitted = splitAbsolutePath(fullPath);
    if (!splitted) return;
    await ensureAppsLoaded();
    const app = getAppByKey('video-player');
    if (!app) {
      message.error(t('App "{key}" not found.', { key: 'video-player' }));
      return;
    }
    const entry: VfsEntry = { name: splitted.name, is_dir: false, size: 0, mtime: 0 };
    openWithApp(entry, app, splitted.dir);
  }, [openWithApp, t]);

  const fetchDetail = useCallback(async (item: VideoLibraryItem) => {
    setDetailLoading(true);
    setDetail(null);
    try {
      const payload = await videoLibraryApi.get(item.id);
      setDetail(payload);
    } catch (err: any) {
      setDetail(null);
      const msg = err instanceof Error ? err.message : t('Load failed');
      message.error(msg);
    } finally {
      setDetailLoading(false);
    }
  }, [t]);

  const openDetail = (item: VideoLibraryItem) => {
    setSelected(item);
    setDetailOpen(true);
    fetchDetail(item);
  };

  const closeDetail = () => {
    setDetailOpen(false);
    setSelected(null);
    setDetail(null);
  };

  const renderCover = (item: VideoLibraryItem) => {
    const label = item.type === 'tv' ? 'TV' : 'Movie';
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

  const detailTitle = useMemo(() => {
    const d = detail?.tmdb?.detail;
    if (!d) return selected?.title || '';
    if (detail?.type === 'tv') return d.name || d.original_name || selected?.title || '';
    return d.title || d.original_title || selected?.title || '';
  }, [detail, selected?.title]);

  const detailPosterUrl = useMemo(() => tmdbImage(detail?.tmdb?.detail?.poster_path, 'w342'), [detail]);
  const detailBackdropUrl = useMemo(() => tmdbImage(detail?.tmdb?.detail?.backdrop_path, 'w1280'), [detail]);

  const detailGenres = useMemo(() => {
    const genres = detail?.tmdb?.detail?.genres;
    if (!Array.isArray(genres)) return [];
    return genres.map((g: any) => g?.name).filter(Boolean);
  }, [detail]);

  const detailOverview = useMemo(() => {
    const overview = detail?.tmdb?.detail?.overview;
    if (!overview) return '';
    return String(overview);
  }, [detail]);

  const castTop = useMemo(() => {
    const cast = detail?.tmdb?.detail?.credits?.cast;
    if (!Array.isArray(cast)) return [];
    return cast.slice(0, 12);
  }, [detail]);

  const episodesBySeason = useMemo(() => {
    if (detail?.type !== 'tv') return [];
    const episodes = Array.isArray(detail?.episodes) ? detail.episodes : [];
    const map = new Map<number, any[]>();
    episodes.forEach((ep: any) => {
      const season = typeof ep?.season === 'number' ? ep.season : 1;
      if (!map.has(season)) map.set(season, []);
      map.get(season)!.push(ep);
    });
    const seasons = Array.from(map.keys()).sort((a, b) => a - b);
    return seasons.map((season) => {
      const list = (map.get(season) || []).slice().sort((a, b) => {
        const ae = typeof a?.episode === 'number' ? a.episode : 10_000;
        const be = typeof b?.episode === 'number' ? b.episode : 10_000;
        return ae - be;
      });
      return { season, episodes: list };
    });
  }, [detail]);

  const renderHero = () => {
    const year = detail?.type === 'tv'
      ? (detail?.tmdb?.detail?.first_air_date || '').slice(0, 4)
      : (detail?.tmdb?.detail?.release_date || '').slice(0, 4);
    const vote = detail?.tmdb?.detail?.vote_average;
    const voteText = typeof vote === 'number' ? vote.toFixed(1) : '--';

    return (
      <div
        style={{
          position: 'relative',
          padding: 16,
          minHeight: 220,
          background: detailBackdropUrl
            ? `url(${detailBackdropUrl}) center / cover no-repeat`
            : 'linear-gradient(135deg, #0b1020 0%, #22314a 55%, #2b3b5c 100%)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(90deg, rgba(2,6,23,0.92) 0%, rgba(2,6,23,0.55) 55%, rgba(2,6,23,0.15) 100%)',
          }}
        />
        <div style={{ position: 'relative', display: 'flex', gap: 16, alignItems: 'flex-end' }}>
          <div style={{ width: 132, flex: 'none' }}>
            <div style={{ borderRadius: 12, overflow: 'hidden', boxShadow: token.boxShadowTertiary, border: '1px solid rgba(255,255,255,0.18)' }}>
              {detailPosterUrl ? (
                <Image
                  src={detailPosterUrl}
                  alt={detailTitle}
                  preview={false}
                  width={132}
                  height={198}
                  style={{ objectFit: 'cover', display: 'block' }}
                  fallback="/logo.svg"
                />
              ) : (
                <div
                  style={{
                    width: 132,
                    height: 198,
                    background: 'rgba(255,255,255,0.08)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    color: 'rgba(255,255,255,0.75)',
                  }}
                >
                  <VideoCameraOutlined style={{ fontSize: 28 }} />
                </div>
              )}
            </div>
          </div>

          <div style={{ minWidth: 0, flex: 1, color: 'rgba(255,255,255,0.92)' }}>
            <Typography.Title level={3} style={{ margin: 0, color: 'rgba(255,255,255,0.92)' }} ellipsis>
              {detailTitle}
            </Typography.Title>
            <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', color: 'rgba(255,255,255,0.72)' }}>
              {year && <span>{year}</span>}
              <span>·</span>
              <span>TMDB {voteText}</span>
              {detail?.type === 'tv' && (
                <>
                  <span>·</span>
                  <span>{episodesBySeason.reduce((acc, s) => acc + s.episodes.length, 0)} {t('Episodes')}</span>
                </>
              )}
            </div>
            <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {(detailGenres || []).slice(0, 6).map((g: string) => (
                <Tag key={g} color="geekblue" style={{ marginInlineEnd: 0 }}>
                  {g}
                </Tag>
              ))}
            </div>
            {detail?.type === 'movie' && (
              <div style={{ marginTop: 14 }}>
                <Button
                  type="primary"
                  icon={<PlayCircleOutlined />}
                  onClick={() => playByPath(String(detail?.source_path || ''))}
                  disabled={!detail?.source_path}
                >
                  {t('Play')}
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  };

  const renderMeta = () => {
    if (!detail?.tmdb?.detail) return null;
    const d = detail.tmdb.detail;
    const isTv = detail?.type === 'tv';
    const release = isTv ? d.first_air_date : d.release_date;
    const runtime = isTv ? (Array.isArray(d.episode_run_time) ? d.episode_run_time[0] : undefined) : d.runtime;
    const status = d.status;
    const language = d.original_language;
    const origin = isTv ? d.original_name : d.original_title;
    const seasons = isTv ? d.number_of_seasons : undefined;
    const eps = isTv ? d.number_of_episodes : undefined;

    return (
      <Descriptions
        size="small"
        column={2}
        styles={{ label: { width: 110, color: token.colorTextSecondary } }}
        style={{ marginTop: 10 }}
      >
        <Descriptions.Item label={t('Type')}>{isTv ? t('TV') : t('Movies')}</Descriptions.Item>
        <Descriptions.Item label="TMDB ID">{String(detail?.tmdb?.id || '')}</Descriptions.Item>
        {origin && <Descriptions.Item label={t('Original Title')}>{String(origin)}</Descriptions.Item>}
        {release && <Descriptions.Item label={t('Release Date')}>{String(release)}</Descriptions.Item>}
        {status && <Descriptions.Item label={t('Status')}>{String(status)}</Descriptions.Item>}
        {runtime && <Descriptions.Item label={t('Runtime')}>{String(runtime)} min</Descriptions.Item>}
        {language && <Descriptions.Item label={t('Language')}>{String(language).toUpperCase()}</Descriptions.Item>}
        {isTv && seasons !== undefined && <Descriptions.Item label={t('Seasons')}>{String(seasons)}</Descriptions.Item>}
        {isTv && eps !== undefined && <Descriptions.Item label={t('Episodes')}>{String(eps)}</Descriptions.Item>}
        {detail?.source_path && <Descriptions.Item label={t('Source Path')} span={2}>{String(detail.source_path)}</Descriptions.Item>}
      </Descriptions>
    );
  };

  const renderCast = () => {
    if (!castTop.length) return null;
    return (
      <div style={{ marginTop: 14 }}>
        <Typography.Title level={5} style={{ margin: 0 }}>
          {t('Cast')}
        </Typography.Title>
        <div style={{ marginTop: 10, display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          {castTop.map((c: any) => {
            const avatar = tmdbImage(c?.profile_path, 'w185');
            return (
              <div
                key={String(c?.id || `${c?.name}-${c?.character}`)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  padding: '8px 10px',
                  borderRadius: 12,
                  background: token.colorFillQuaternary,
                  border: `1px solid ${token.colorBorderSecondary}`,
                  minWidth: 200,
                }}
              >
                <Avatar size={36} src={avatar} style={{ flex: 'none' }}>
                  {(c?.name || '?').slice(0, 1)}
                </Avatar>
                <div style={{ minWidth: 0 }}>
                  <Typography.Text strong ellipsis style={{ display: 'block', maxWidth: 140 }}>
                    {c?.name || '--'}
                  </Typography.Text>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }} ellipsis>
                    {c?.character || ''}
                  </Typography.Text>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderEpisodes = () => {
    if (detail?.type !== 'tv') return null;
    if (!episodesBySeason.length) {
      return (
        <Empty description={t('No data')} style={{ marginTop: 24 }} />
      );
    }

    return (
      <Collapse
        accordion={false}
        items={episodesBySeason.map(({ season, episodes }) => ({
          key: String(season),
          label: `${t('Season')} ${season} · ${episodes.length} ${t('Episodes')}`,
          children: (
            <List
              itemLayout="horizontal"
              dataSource={episodes}
              renderItem={(ep: any) => {
                const seasonNo = typeof ep?.season === 'number' ? ep.season : season;
                const epNo = typeof ep?.episode === 'number' ? ep.episode : undefined;
                const tmdbEp = ep?.tmdb_episode || {};
                const still = tmdbImage(tmdbEp?.still_path, 'w300');
                const title = tmdbEp?.name || ep?.name || ep?.rel || '--';
                const air = tmdbEp?.air_date ? String(tmdbEp.air_date) : '';
                const runtime = tmdbEp?.runtime ? `${tmdbEp.runtime} min` : '';
                const sub = [air, runtime].filter(Boolean).join(' · ');
                const prefix = epNo !== undefined ? `S${String(seasonNo).padStart(2, '0')}E${String(epNo).padStart(2, '0')}` : `S${String(seasonNo).padStart(2, '0')}`;

                return (
                  <List.Item
                    style={{ paddingInline: 0 }}
                    actions={[
                      <Button
                        key="play"
                        type="primary"
                        icon={<PlayCircleOutlined />}
                        onClick={() => playByPath(String(ep?.path || ''))}
                        disabled={!ep?.path}
                      >
                        {t('Play')}
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      avatar={still ? (
                        <Image
                          src={still}
                          preview={false}
                          width={120}
                          height={68}
                          style={{ objectFit: 'cover', borderRadius: 10, overflow: 'hidden' }}
                          fallback="/logo.svg"
                        />
                      ) : (
                        <div
                          style={{
                            width: 120,
                            height: 68,
                            borderRadius: 10,
                            background: token.colorFillQuaternary,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: token.colorTextTertiary,
                          }}
                        >
                          <VideoCameraOutlined />
                        </div>
                      )}
                      title={(
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <Tag style={{ marginInlineEnd: 0 }}>{prefix}</Tag>
                          <Typography.Text strong ellipsis style={{ display: 'block', maxWidth: 360 }}>
                            {title}
                          </Typography.Text>
                        </div>
                      )}
                      description={sub ? <Typography.Text type="secondary">{sub}</Typography.Text> : null}
                    />
                  </List.Item>
                );
              }}
            />
          ),
        }))}
      />
    );
  };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgLayout }}>
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
              {t('Total')}: {stats.total} · {t('Movies')}: {stats.movie} · {t('TV')}: {stats.tv}
            </Typography.Text>
          </div>
          <Space size={10} wrap>
            <Segmented
              value={filter}
              onChange={(v) => setFilter(v as LibraryFilter)}
              options={[
                { value: 'all', label: t('All') },
                { value: 'movie', label: t('Movies') },
                { value: 'tv', label: t('TV') },
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

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', padding: '12px 2px' }}>
        {loading ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 }}>
            {Array.from({ length: 10 }).map((_, idx) => (
	              <Card
	                key={idx}
	                size="small"
	                style={{ borderRadius: 12, overflow: 'hidden' }}
	                cover={(
	                  <div style={{ width: '100%', aspectRatio: '2 / 3' }}>
	                    <Skeleton.Image active style={{ width: '100%', height: '100%' }} />
	                  </div>
	                )}
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
                styles={{ body: { padding: 10 } } as any}
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
                  {v.type === 'tv' ? (
                    <>
                      <span>·</span>
                      <span>{v.episodes_count || 0} {t('Episodes')}</span>
                    </>
                  ) : null}
                </div>
                <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {(v.genres || []).slice(0, 3).map((tag) => (
                    <Tag key={tag} style={{ marginInlineEnd: 0 }}>
                      {tag}
                    </Tag>
                  ))}
                  {(v.genres || []).length > 3 && (
                    <Tag style={{ marginInlineEnd: 0 }}>+{(v.genres || []).length - 3}</Tag>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Drawer
        title={detailTitle || selected?.title || t('Details')}
        open={detailOpen}
        onClose={closeDetail}
        width="100%"
        destroyOnHidden
        getContainer={false}
        styles={{ body: { padding: 0 } }}
      >
        {detailLoading ? (
          <div style={{ padding: 16 }}>
            <Skeleton active paragraph={{ rows: 10 }} />
          </div>
        ) : !detail ? (
          <Empty description={t('No data')} style={{ marginTop: 48 }} />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {renderHero()}
            <div style={{ padding: 16 }}>
              <Tabs
                items={[
                  ...(detail?.type === 'tv'
                    ? [{
                      key: 'episodes',
                      label: t('Episodes'),
                      children: renderEpisodes(),
                    }]
                    : []),
                  {
                    key: 'detail',
                    label: t('Details'),
                    children: (
                      <>
                        {renderMeta()}
                        {detailOverview && (
                          <>
                            <Divider style={{ margin: '14px 0' }} />
                            <Typography.Title level={5} style={{ margin: 0 }}>
                              {t('Overview')}
                            </Typography.Title>
                            <Typography.Paragraph style={{ marginTop: 8, whiteSpace: 'pre-wrap' }}>
                              {detailOverview}
                            </Typography.Paragraph>
                          </>
                        )}
                        {renderCast()}
                      </>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
};
