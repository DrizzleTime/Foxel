/**
 * 视频库插件前端入口
 *
 * 注意：这是一个示例，实际开发时应使用 TSX 编写并通过 Vite 打包
 * 此文件展示了插件如何使用宿主提供的依赖
 */

(function () {
  'use strict';

  // 获取宿主依赖
  const externals = window.__FOXEL_EXTERNALS__;
  if (!externals) {
    console.error('[video-library] Foxel externals not found');
    return;
  }

  const { React, ReactDOM, antd, AntdIcons, foxelApi } = externals;
  const { useState, useEffect, useCallback, useMemo, useRef } = React;
  const {
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
    List,
    Tabs,
    Collapse,
    Avatar,
    Divider,
    Descriptions,
    theme,
  } = antd;
  const {
    SearchOutlined,
    ReloadOutlined,
    PlayCircleOutlined,
    VideoCameraOutlined,
  } = AntdIcons;

  const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/';

  function tmdbImage(path, size) {
    if (!path) return undefined;
    return `${TMDB_IMAGE_BASE}${size}${path}`;
  }

  // 视频库列表 API
  async function fetchLibrary() {
    const resp = await foxelApi.request('/plugins/video-library/library');
    return resp;
  }

  async function fetchLibraryItem(id) {
    const resp = await foxelApi.request(`/plugins/video-library/library/${id}`);
    return resp;
  }

  // 视频库应用组件
  function VideoLibraryApp({ host }) {
    const { token } = theme.useToken();
    const [q, setQ] = useState('');
    const [filter, setFilter] = useState('all');
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const [detailOpen, setDetailOpen] = useState(false);
    const [selected, setSelected] = useState(null);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detail, setDetail] = useState(null);

    const loadLibrary = useCallback(async () => {
      setLoading(true);
      try {
        const list = await fetchLibrary();
        setItems(list || []);
      } catch (err) {
        setItems([]);
        message.error(err?.message || '加载失败');
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

    const fetchDetail = useCallback(async (item) => {
      setDetailLoading(true);
      setDetail(null);
      try {
        const payload = await fetchLibraryItem(item.id);
        setDetail(payload);
      } catch (err) {
        setDetail(null);
        message.error(err?.message || '加载失败');
      } finally {
        setDetailLoading(false);
      }
    }, []);

    const openDetail = (item) => {
      setSelected(item);
      setDetailOpen(true);
      fetchDetail(item);
    };

    const closeDetail = () => {
      setDetailOpen(false);
      setSelected(null);
      setDetail(null);
    };

    const renderCover = (item) => {
      const label = item.type === 'tv' ? 'TV' : 'Movie';
      const coverUrl = tmdbImage(item.poster_path, 'w342') || tmdbImage(item.backdrop_path, 'w780');
      return React.createElement(
        'div',
        {
          style: {
            position: 'relative',
            width: '100%',
            aspectRatio: '2 / 3',
            background: 'linear-gradient(135deg, #0b1020 0%, #22314a 55%, #2b3b5c 100%)',
            overflow: 'hidden',
          },
        },
        coverUrl
          ? React.createElement(Image, {
              src: coverUrl,
              alt: item.title || label,
              preview: false,
              wrapperStyle: { width: '100%', height: '100%', display: 'block' },
              style: { width: '100%', height: '100%', objectFit: 'cover', display: 'block' },
              fallback: '/logo.svg',
            })
          : React.createElement(
              'div',
              {
                style: {
                  position: 'absolute',
                  inset: 0,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'rgba(255,255,255,0.7)',
                },
              },
              React.createElement(VideoCameraOutlined, { style: { fontSize: 28 } })
            ),
        React.createElement('div', {
          style: {
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(180deg, rgba(0,0,0,0.48) 0%, rgba(0,0,0,0.12) 40%, rgba(0,0,0,0.45) 100%)',
            pointerEvents: 'none',
          },
        }),
        React.createElement(
          'div',
          {
            style: {
              position: 'absolute',
              top: 10,
              left: 10,
              right: 10,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 8,
              pointerEvents: 'none',
            },
          },
          React.createElement(Tag, { color: item.type === 'tv' ? 'geekblue' : 'gold', style: { marginInlineEnd: 0 } }, label),
          React.createElement(VideoCameraOutlined, { style: { fontSize: 18, opacity: 0.9, color: 'rgba(255,255,255,0.9)' } })
        ),
        React.createElement(
          'div',
          {
            style: {
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
            },
          },
          React.createElement(PlayCircleOutlined, { style: { fontSize: 20 } })
        )
      );
    };

    return React.createElement(
      'div',
      { style: { height: '100%', display: 'flex', flexDirection: 'column', background: token.colorBgLayout } },
      // Header
      React.createElement(
        'div',
        {
          style: {
            padding: 14,
            borderRadius: 12,
            background: token.colorBgContainer,
            border: `1px solid ${token.colorBorderSecondary}`,
          },
        },
        React.createElement(
          Flex,
          { align: 'center', justify: 'space-between', gap: 12, wrap: true },
          React.createElement(
            'div',
            { style: { minWidth: 240 } },
            React.createElement(Typography.Title, { level: 4, style: { margin: 0 } }, '视频库'),
            React.createElement(
              Typography.Text,
              { type: 'secondary' },
              `总计: ${stats.total} · 电影: ${stats.movie} · 电视剧: ${stats.tv}`
            )
          ),
          React.createElement(
            Space,
            { size: 10, wrap: true },
            React.createElement(Segmented, {
              value: filter,
              onChange: (v) => setFilter(v),
              options: [
                { value: 'all', label: '全部' },
                { value: 'movie', label: '电影' },
                { value: 'tv', label: '电视剧' },
              ],
            }),
            React.createElement(Input, {
              allowClear: true,
              value: q,
              onChange: (e) => setQ(e.target.value),
              prefix: React.createElement(SearchOutlined),
              placeholder: '搜索',
              style: { width: 260 },
            }),
            React.createElement(
              Button,
              { icon: React.createElement(ReloadOutlined), onClick: loadLibrary, loading: loading },
              '刷新'
            )
          )
        )
      ),
      // Content
      React.createElement(
        'div',
        { style: { flex: 1, minHeight: 0, overflow: 'auto', padding: '12px 2px' } },
        loading
          ? React.createElement(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 } },
              Array.from({ length: 10 }).map((_, idx) =>
                React.createElement(
                  Card,
                  {
                    key: idx,
                    size: 'small',
                    style: { borderRadius: 12, overflow: 'hidden' },
                    cover: React.createElement(
                      'div',
                      { style: { width: '100%', aspectRatio: '2 / 3' } },
                      React.createElement(Skeleton.Image, { active: true, style: { width: '100%', height: '100%' } })
                    ),
                  },
                  React.createElement(Skeleton, { active: true, paragraph: { rows: 2 } })
                )
              )
            )
          : filtered.length === 0
          ? React.createElement(Empty, { description: '暂无数据', style: { marginTop: 48 } })
          : React.createElement(
              'div',
              { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(210px, 1fr))', gap: 12 } },
              filtered.map((v) =>
                React.createElement(
                  Card,
                  {
                    key: v.id,
                    hoverable: true,
                    size: 'small',
                    styles: { body: { padding: 10 } },
                    style: {
                      borderRadius: 12,
                      overflow: 'hidden',
                      boxShadow: token.boxShadowTertiary,
                      border: `1px solid ${token.colorBorderSecondary}`,
                    },
                    cover: renderCover(v),
                    onClick: () => openDetail(v),
                  },
                  React.createElement(Typography.Text, { strong: true, ellipsis: true, style: { display: 'block' } }, v.title || '--'),
                  React.createElement(
                    'div',
                    { style: { marginTop: 6, display: 'flex', gap: 8, color: token.colorTextTertiary, fontSize: 12 } },
                    React.createElement('span', null, v.year || '--'),
                    v.type === 'tv'
                      ? React.createElement(React.Fragment, null, React.createElement('span', null, '·'), React.createElement('span', null, `${v.episodes_count || 0} 集`))
                      : null
                  ),
                  React.createElement(
                    'div',
                    { style: { marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 6 } },
                    (v.genres || []).slice(0, 3).map((tag) => React.createElement(Tag, { key: tag, style: { marginInlineEnd: 0 } }, tag)),
                    (v.genres || []).length > 3 && React.createElement(Tag, { style: { marginInlineEnd: 0 } }, `+${(v.genres || []).length - 3}`)
                  )
                )
              )
            )
      ),
      // Detail Drawer
      React.createElement(
        Drawer,
        {
          title: selected?.title || '详情',
          open: detailOpen,
          onClose: closeDetail,
          width: '100%',
          destroyOnClose: true,
          styles: { body: { padding: 0 } },
        },
        detailLoading
          ? React.createElement('div', { style: { padding: 16 } }, React.createElement(Skeleton, { active: true, paragraph: { rows: 10 } }))
          : !detail
          ? React.createElement(Empty, { description: '暂无数据', style: { marginTop: 48 } })
          : React.createElement(
              'div',
              { style: { padding: 16 } },
              React.createElement(Typography.Title, { level: 4 }, detail.tmdb?.detail?.title || detail.tmdb?.detail?.name || '--'),
              React.createElement(Typography.Paragraph, null, detail.tmdb?.detail?.overview || '暂无简介')
            )
      )
    );
  }

  // 视频播放器组件
  function VideoPlayerApp({ filePath, entry, urls, host }) {
    const containerRef = useRef(null);

    useEffect(() => {
      // 简单的视频播放器
      if (containerRef.current) {
        const video = document.createElement('video');
        video.src = urls.streamUrl || urls.downloadUrl;
        video.controls = true;
        video.autoplay = true;
        video.style.width = '100%';
        video.style.height = '100%';
        video.style.backgroundColor = '#000';
        containerRef.current.innerHTML = '';
        containerRef.current.appendChild(video);
      }
    }, [urls]);

    return React.createElement('div', {
      ref: containerRef,
      style: { width: '100%', height: '100%', backgroundColor: '#000' },
    });
  }

  // 注册插件
  window.FoxelRegister({
    // 文件打开模式
    mount: (container, ctx) => {
      const root = ReactDOM.createRoot(container);
      root.render(React.createElement(VideoPlayerApp, ctx));
      return () => root.unmount();
    },

    // 独立应用模式
    mountApp: (container, ctx) => {
      const root = ReactDOM.createRoot(container);
      root.render(React.createElement(VideoLibraryApp, { host: ctx.host }));
      return () => root.unmount();
    },
  });
})();

