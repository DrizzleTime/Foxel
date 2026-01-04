/**
 * 图片查看器插件前端入口
 */
(function () {
  'use strict';

  const externals = window.__FOXEL_EXTERNALS__;
  if (!externals) {
    console.error('[image-viewer] Foxel externals not found');
    return;
  }

  const { React, ReactDOM, antd, AntdIcons, foxelApi } = externals;
  const { useState, useEffect, useCallback, useMemo, useRef } = React;
  const { Spin, Button, Tooltip, Typography, Empty } = antd;
  const {
    LeftOutlined,
    RightOutlined,
    ZoomInOutlined,
    ZoomOutOutlined,
    RotateRightOutlined,
    ReloadOutlined,
    CompressOutlined,
    CloseOutlined,
    FileOutlined,
    DatabaseOutlined,
    ExpandOutlined,
    BgColorsOutlined,
    ClockCircleOutlined,
    FolderOutlined,
    AimOutlined,
    BulbOutlined,
    ThunderboltOutlined,
    AlertOutlined,
    CameraOutlined,
    ApiOutlined,
    FieldTimeOutlined,
  } = AntdIcons;

  const DEFAULT_TONE = { r: 28, g: 32, b: 46 };

  // ========== 工具函数 ==========

  const isImageEntry = (ent) => {
    if (ent.is_dir) return false;
    if (typeof ent.has_thumbnail === 'boolean' && ent.has_thumbnail) return true;
    const ext = ent.name.split('.').pop()?.toLowerCase();
    if (!ext) return false;
    return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'ico', 'tif', 'tiff', 'svg', 'heic', 'heif', 'arw', 'cr2', 'cr3', 'nef', 'rw2', 'orf', 'pef', 'dng'].includes(ext);
  };

  const buildThumbUrl = (fullPath, w = 180, h = 120) => {
    const base = foxelApi.baseUrl.replace(/\/+$/, '');
    const clean = fullPath.replace(/^\/+/, '');
    return `${base}/fs/thumb/${encodeURI(clean)}?w=${w}&h=${h}&fit=cover`;
  };

  const getDirectory = (fullPath) => {
    const path = fullPath.startsWith('/') ? fullPath : `/${fullPath}`;
    const idx = path.lastIndexOf('/');
    if (idx <= 0) return '/';
    return path.slice(0, idx) || '/';
  };

  const joinPath = (dir, name) => {
    if (dir === '/' || dir === '') return `/${name}`;
    return `${dir.replace(/\/$/, '')}/${name}`;
  };

  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  const parseNumberish = (raw) => {
    if (typeof raw === 'number') return raw;
    if (typeof raw !== 'string') return null;
    if (raw.includes('/')) {
      const [a, b] = raw.split('/').map(v => Number(v));
      if (!Number.isNaN(a) && !Number.isNaN(b) && b !== 0) return a / b;
    }
    const val = Number(raw);
    return Number.isNaN(val) ? null : val;
  };

  const humanFileSize = (size) => {
    if (typeof size !== 'number') return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = size;
    let index = 0;
    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }
    return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  };

  const readExplorerSnapshot = (dir) => {
    if (typeof window === 'undefined') return null;
    const snap = window.__FOXEL_LAST_EXPLORER_PAGE__;
    if (!snap) return null;
    const snapshotPath = snap.path === '' ? '/' : snap.path;
    const normalizedSnap = snapshotPath.endsWith('/') && snapshotPath !== '/' ? snapshotPath.slice(0, -1) : snapshotPath;
    const normalizedTarget = dir.endsWith('/') && dir !== '/' ? dir.slice(0, -1) : dir;
    if (normalizedSnap !== normalizedTarget) return null;
    return snap;
  };

  const formatDateTime = (ts) => {
    if (!ts) return '-';
    try {
      return new Date(ts * 1000).toLocaleString();
    } catch {
      return '-';
    }
  };

  const clampChannel = (value) => Math.max(0, Math.min(255, value));

  const mixColor = (base, target, ratio) => ({
    r: clampChannel(base.r * (1 - ratio) + target.r * ratio),
    g: clampChannel(base.g * (1 - ratio) + target.g * ratio),
    b: clampChannel(base.b * (1 - ratio) + target.b * ratio),
  });

  const rgbToRgba = (color, alpha) => `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${alpha})`;

  const computeImageStats = (img) => {
    try {
      const maxSide = 720;
      const naturalWidth = img.naturalWidth || 1;
      const naturalHeight = img.naturalHeight || 1;
      const ratio = Math.min(1, maxSide / Math.max(naturalWidth, naturalHeight));
      const width = Math.max(1, Math.floor(naturalWidth * ratio));
      const height = Math.max(1, Math.floor(naturalHeight * ratio));
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      if (!ctx) return { histogram: null, dominantColor: null };
      ctx.drawImage(img, 0, 0, width, height);
      const { data } = ctx.getImageData(0, 0, width, height);
      const r = new Array(256).fill(0);
      const g = new Array(256).fill(0);
      const b = new Array(256).fill(0);
      let rTotal = 0;
      let gTotal = 0;
      let bTotal = 0;
      let count = 0;
      for (let i = 0; i < data.length; i += 4) {
        r[data[i]] += 1;
        g[data[i + 1]] += 1;
        b[data[i + 2]] += 1;
        rTotal += data[i];
        gTotal += data[i + 1];
        bTotal += data[i + 2];
        count += 1;
      }
      const histogram = { r, g, b };
      if (count === 0) return { histogram, dominantColor: null };
      const dominantColor = {
        r: rTotal / count,
        g: gTotal / count,
        b: bTotal / count,
      };
      return { histogram, dominantColor };
    } catch {
      return { histogram: null, dominantColor: null };
    }
  };

  // ========== 样式 ==========

  const viewerStyles = {
    container: {
      width: '100%',
      height: '100%',
      boxSizing: 'border-box',
      display: 'grid',
      gridTemplateColumns: 'minmax(0, 1fr) 320px',
      columnGap: 0,
      color: '#fff',
      overflow: 'hidden',
    },
    main: {
      position: 'relative',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '0 28px 80px rgba(0,0,0,0.55)',
      minHeight: 0,
    },
    mainBackdrop: {
      position: 'absolute',
      inset: 0,
    },
    mainContent: {
      position: 'relative',
      zIndex: 1,
      display: 'flex',
      flexDirection: 'column',
      flex: 1,
      padding: 0,
      minHeight: 0,
      minWidth: 0,
    },
    viewer: {
      flex: 1,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      position: 'relative',
      overflow: 'hidden',
      boxShadow: '0 24px 60px rgba(0,0,0,0.5)',
      touchAction: 'none',
      minHeight: 0,
    },
    controls: {
      position: 'absolute',
      bottom: 16,
      left: '50%',
      transform: 'translateX(-50%)',
      display: 'flex',
      gap: 16,
      padding: '8px 18px',
      borderRadius: 24,
      alignItems: 'center',
    },
    scaleBadge: {
      position: 'absolute',
      bottom: 64,
      left: 16,
      color: 'rgba(255,255,255,0.7)',
      fontSize: 12,
      letterSpacing: 0.2,
    },
    filmstripShell: {
      marginTop: 0,
      padding: '3px 12px',
      boxShadow: '0 16px 42px rgba(0,0,0,0.52)',
    },
    filmstrip: {
      display: 'flex',
      overflowX: 'auto',
      gap: 12,
      paddingBottom: 4,
    },
    sidePanel: {
      boxShadow: '0 28px 80px rgba(0,0,0,0.55)',
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      overflowY: 'auto',
      minHeight: 0,
    },
    histogramCard: {
      padding: '12px 12px 18px',
      background: 'rgba(0,0,0,0.34)',
      borderRadius: 0,
    },
    viewerCloseWrap: {
      position: 'absolute',
      top: 16,
      right: 16,
      zIndex: 2,
    },
    viewerClose: {
      color: '#fff',
      background: 'rgba(0,0,0,0.4)',
      border: '1px solid rgba(255,255,255,0.25)',
      boxShadow: '0 8px 18px rgba(0,0,0,0.45)',
      borderRadius: '100%',
      width: 32,
      height: 32,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
    },
  };

  // ========== 子组件 ==========

  function HistogramPlot({ data }) {
    if (!data) {
      return React.createElement(Empty, { description: '无法解析直方图', image: Empty.PRESENTED_IMAGE_SIMPLE });
    }
    const width = 260;
    const height = 140;
    const max = Math.max(...data.r, ...data.g, ...data.b, 1);
    const toPath = (arr) => arr
      .map((value, index) => {
        const x = (index / 255) * width;
        const y = height - (value / max) * height;
        return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(' ');
    return React.createElement('svg', { width, height, viewBox: `0 0 ${width} ${height}`, style: { width: '100%' } },
      React.createElement('rect', { x: 0, y: 0, width, height, fill: 'rgba(255,255,255,0.04)' }),
      React.createElement('path', { d: toPath(data.r), stroke: 'rgba(255,99,132,0.88)', fill: 'none', strokeWidth: 1.3 }),
      React.createElement('path', { d: toPath(data.g), stroke: 'rgba(75,192,192,0.88)', fill: 'none', strokeWidth: 1.3 }),
      React.createElement('path', { d: toPath(data.b), stroke: 'rgba(54,162,235,0.88)', fill: 'none', strokeWidth: 1.3 })
    );
  }

  function SectionTitle({ children }) {
    return React.createElement(Typography.Title, {
      level: 5,
      style: { color: '#fff', fontSize: 15, marginTop: 24, marginBottom: 12 },
    }, children);
  }

  function InfoRows({ items }) {
    const filtered = items.filter(item => item.value !== null && item.value !== undefined && item.value !== '');
    return React.createElement('div', {
      style: { display: 'grid', gridTemplateColumns: '100px 1fr', rowGap: 10, columnGap: 12 }
    }, filtered.map(item => React.createElement(React.Fragment, { key: item.label },
      React.createElement('span', {
        style: { display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.55)' }
      },
        item.icon && React.createElement('span', { style: { display: 'inline-flex', alignItems: 'center' } }, item.icon),
        React.createElement('span', null, item.label)
      ),
      React.createElement('span', { style: { color: '#fff', wordBreak: 'break-all' } }, item.value)
    )));
  }

  function ViewerControls({ style, onPrev, onNext, onZoomIn, onZoomOut, onRotate, onReset, onFit, disableSwitch }) {
    const btn = (title, icon, onClick, disabled = false) =>
      React.createElement(Tooltip, { title, key: title },
        React.createElement(Button, {
          shape: 'circle',
          type: 'text',
          icon: React.createElement(icon),
          onClick,
          disabled,
          style: { color: '#fff' }
        })
      );
    return React.createElement('div', { style },
      btn('上一张', LeftOutlined, onPrev, disableSwitch),
      btn('缩小', ZoomOutOutlined, onZoomOut),
      btn('放大', ZoomInOutlined, onZoomIn),
      btn('旋转 90°', RotateRightOutlined, onRotate),
      btn('重置', ReloadOutlined, onReset),
      btn('适应窗口', CompressOutlined, onFit),
      btn('下一张', RightOutlined, onNext, disableSwitch)
    );
  }

  function Filmstrip({ shellStyle, listStyle, entries, activeEntry, onSelect, filmstripRefs, pageInfo, getThumbUrl }) {
    return React.createElement('div', { style: shellStyle },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 } },
        React.createElement(Typography.Text, { style: { color: 'rgba(255,255,255,0.72)', fontWeight: 500 } },
          `胶片带 · ${entries.length} 张`
        ),
        pageInfo && React.createElement(Typography.Text, { style: { color: 'rgba(255,255,255,0.45)', fontSize: 12 } },
          `第 ${pageInfo.page} 页 / 共 ${Math.max(1, Math.ceil(pageInfo.total / pageInfo.pageSize))} 页`
        )
      ),
      React.createElement('div', { style: listStyle },
        entries.map(item => {
          const active = item.name === activeEntry.name;
          return React.createElement('div', {
            key: `${item.name}-${item.mtime || ''}`,
            ref: el => { filmstripRefs.current[item.name] = el; },
            onClick: () => onSelect(item),
            style: {
              width: 84,
              height: 64,
              overflow: 'hidden',
              border: active ? '2px solid #4e9bff' : '2px solid transparent',
              boxShadow: active ? '0 0 0 4px rgba(78,155,255,0.28)' : '0 10px 28px rgba(0,0,0,0.45)',
              cursor: 'pointer',
              position: 'relative',
              flex: '0 0 auto',
            },
          },
            React.createElement('img', {
              src: getThumbUrl(item),
              alt: item.name,
              style: { width: '100%', height: '100%', objectFit: 'cover', filter: active ? 'saturate(1)' : 'saturate(0.65)' }
            }),
            active && React.createElement('div', {
              style: {
                position: 'absolute',
                bottom: 4,
                left: 6,
                right: 6,
                padding: '2px 4px',
                background: 'rgba(0,0,0,0.55)',
                color: '#fff',
                fontSize: 10,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              },
            }, item.name)
          );
        }),
        entries.length === 0 && React.createElement('div', { style: { color: 'rgba(255,255,255,0.45)' } }, '暂无图片')
      )
    );
  }

  function InfoPanel({ style, histogramCardStyle, title, captureTime, basicList, shootingList, deviceList, miscList, histogram }) {
    return React.createElement('aside', { style },
      React.createElement(Typography.Title, { level: 3, style: { color: '#fff', marginTop: 6, wordBreak: 'break-all' } }, title),
      captureTime && React.createElement(Typography.Text, { style: { color: 'rgba(255,255,255,0.6)' } }, `拍摄时间 ${captureTime}`),
      React.createElement(SectionTitle, null, '基本信息'),
      React.createElement(InfoRows, { items: basicList }),
      shootingList.some(i => i.value) && React.createElement(React.Fragment, null,
        React.createElement(SectionTitle, null, '拍摄参数'),
        React.createElement(InfoRows, { items: shootingList })
      ),
      deviceList.some(i => i.value) && React.createElement(React.Fragment, null,
        React.createElement(SectionTitle, null, '设备信息'),
        React.createElement(InfoRows, { items: deviceList })
      ),
      miscList.some(i => i.value) && React.createElement(React.Fragment, null,
        React.createElement(SectionTitle, null, '其他'),
        React.createElement(InfoRows, { items: miscList })
      ),
      React.createElement(SectionTitle, null, '直方图'),
      React.createElement('div', { style: histogramCardStyle },
        React.createElement(HistogramPlot, { data: histogram }),
        React.createElement('div', { style: { marginTop: 12, display: 'flex', gap: 12, fontSize: 12 } },
          React.createElement('span', { style: { color: 'rgba(255,99,132,0.88)' } }, 'R'),
          React.createElement('span', { style: { color: 'rgba(75,192,192,0.88)' } }, 'G'),
          React.createElement('span', { style: { color: 'rgba(54,162,235,0.88)' } }, 'B')
        )
      )
    );
  }

  // ========== 主组件 ==========

  function ImageViewerApp({ filePath, entry, urls, host }) {
    const normalizedInitialPath = filePath.startsWith('/') ? filePath : `/${filePath}`;
    const [activeEntry, setActiveEntry] = useState(entry);
    const [activePath, setActivePath] = useState(normalizedInitialPath);
    const [imageUrl, setImageUrl] = useState();
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState();
    const [stat, setStat] = useState(null);
    const [histogram, setHistogram] = useState(null);
    const [dominantColor, setDominantColor] = useState(null);
    const [scale, setScale] = useState(1);
    const [offset, setOffset] = useState({ x: 0, y: 0 });
    const [rotate, setRotate] = useState(0);
    const [isDragging, setIsDragging] = useState(false);
    const [filmstrip, setFilmstrip] = useState([]);
    const [pageInfo, setPageInfo] = useState(null);

    const containerRef = useRef(null);
    const imageRef = useRef(null);
    const dragPointRef = useRef(null);
    const pinchDistanceRef = useRef(null);
    const transitionRef = useRef(false);
    const filmstripRefs = useRef({});

    const directory = useMemo(() => getDirectory(activePath), [activePath]);
    const baseTone = useMemo(() => dominantColor || DEFAULT_TONE, [dominantColor]);

    const containerStyle = useMemo(() => {
      const light = mixColor(baseTone, { r: 255, g: 255, b: 255 }, 0.18);
      const shadow = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.62);
      return {
        ...viewerStyles.container,
        background: `linear-gradient(135deg, ${rgbToRgba(light, 0.78)} 0%, ${rgbToRgba(baseTone, 0.86)} 48%, ${rgbToRgba(shadow, 0.96)} 100%)`,
      };
    }, [baseTone]);

    const mainBackdropStyle = useMemo(() => {
      const glow = mixColor(baseTone, { r: 255, g: 255, b: 255 }, 0.32);
      const shade = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.7);
      return {
        ...viewerStyles.mainBackdrop,
        background: `radial-gradient(circle at 18% 22%, ${rgbToRgba(glow, 0.38)}, ${rgbToRgba(shade, 0.94)} 68%)`,
      };
    }, [baseTone]);

    const viewerStyle = useMemo(() => {
      const surface = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.45);
      const edge = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.65);
      return {
        ...viewerStyles.viewer,
        background: `linear-gradient(145deg, ${rgbToRgba(surface, 0.7)} 0%, ${rgbToRgba(edge, 0.92)} 100%)`,
        backdropFilter: 'blur(28px)',
      };
    }, [baseTone]);

    const controlsStyle = useMemo(() => {
      const tone = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.52);
      return {
        ...viewerStyles.controls,
        background: rgbToRgba(tone, 0.74),
        backdropFilter: 'blur(18px)',
      };
    }, [baseTone]);

    const filmstripShellStyle = useMemo(() => {
      const tone = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.56);
      return {
        ...viewerStyles.filmstripShell,
        background: rgbToRgba(tone, 0.7),
        backdropFilter: 'blur(22px)',
      };
    }, [baseTone]);

    const getThumbUrl = useCallback((item) => {
      const full = joinPath(directory, item.name);
      return buildThumbUrl(full, 160, 120);
    }, [directory]);

    const sidePanelStyle = useMemo(() => {
      const panel = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.6);
      const border = rgbToRgba(mixColor(baseTone, { r: 255, g: 255, b: 255 }, 0.1), 0.28);
      return {
        ...viewerStyles.sidePanel,
        background: rgbToRgba(panel, 0.8),
        backdropFilter: 'blur(28px)',
        borderLeft: `1px solid ${border}`,
      };
    }, [baseTone]);

    const histogramCardStyle = useMemo(() => {
      const tone = mixColor(baseTone, { r: 0, g: 0, b: 0 }, 0.55);
      const stroke = rgbToRgba(mixColor(baseTone, { r: 255, g: 255, b: 255 }, 0.12), 0.2);
      return {
        ...viewerStyles.histogramCard,
        background: rgbToRgba(tone, 0.58),
        border: `1px solid ${stroke}`,
      };
    }, [baseTone]);

    useEffect(() => {
      const normalized = filePath.startsWith('/') ? filePath : `/${filePath}`;
      setActiveEntry(entry);
      setActivePath(normalized);
    }, [entry, filePath]);

    useEffect(() => {
      let cancelled = false;
      setLoading(true);
      setError(undefined);
      setHistogram(null);
      setDominantColor(null);
      const cleaned = activePath.replace(/^\/+/, '');

      Promise.all([
        foxelApi.request(`/fs/temp-link/${encodeURI(cleaned)}`),
        foxelApi.request(`/fs/stat/${encodeURI(cleaned)}`),
      ])
        .then(([tokenRes, metadata]) => {
          if (cancelled) return;
          const publicUrl = `${foxelApi.baseUrl}/fs/temp/${tokenRes.token}`;
          setImageUrl(publicUrl);
          setStat(metadata);
          setScale(1);
          setRotate(0);
          setOffset({ x: 0, y: 0 });
        })
        .catch((err) => {
          if (!cancelled) {
            setError(err instanceof Error ? err.message : '加载失败');
          }
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
      return () => {
        cancelled = true;
      };
    }, [activePath]);

    const refreshFilmstrip = useCallback((dir) => {
      const snap = readExplorerSnapshot(dir);
      if (snap) {
        const images = snap.entries.filter(isImageEntry);
        const ensured = images.some(item => item.name === activeEntry.name) ? images : [...images, activeEntry];
        setFilmstrip(ensured);
        if (snap.pagination) {
          setPageInfo({
            page: snap.pagination.page,
            pageSize: snap.pagination.page_size,
            total: snap.pagination.total,
          });
        } else {
          setPageInfo(null);
        }
        return;
      }
      setFilmstrip([activeEntry]);
      setPageInfo(null);
    }, [activeEntry]);

    useEffect(() => {
      refreshFilmstrip(directory);
    }, [directory, refreshFilmstrip]);

    useEffect(() => {
      const handler = () => refreshFilmstrip(directory);
      window.addEventListener('foxel:file-explorer-page', handler);
      return () => window.removeEventListener('foxel:file-explorer-page', handler);
    }, [directory, refreshFilmstrip]);

    useEffect(() => {
      const el = filmstripRefs.current[activeEntry.name];
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
      }
    }, [activeEntry, filmstrip]);

    const zoom = useCallback((factor) => {
      setScale(prev => {
        const next = clamp(prev * factor, 0.08, 10);
        transitionRef.current = true;
        window.setTimeout(() => { transitionRef.current = false; }, 120);
        return next;
      });
    }, []);

    const rotateImage = () => {
      setRotate(prev => {
        transitionRef.current = true;
        window.setTimeout(() => { transitionRef.current = false; }, 180);
        return (prev + 90) % 360;
      });
    };

    const resetView = () => {
      transitionRef.current = true;
      window.setTimeout(() => { transitionRef.current = false; }, 160);
      setScale(1);
      setOffset({ x: 0, y: 0 });
      setRotate(0);
    };

    const fitToScreen = () => {
      resetView();
    };

    const switchEntry = (target) => {
      const nextPath = joinPath(directory, target.name);
      setActiveEntry(target);
      setActivePath(nextPath);
    };

    const switchRelative = (step) => {
      if (filmstrip.length <= 1) return;
      const currentIndex = filmstrip.findIndex(item => item.name === activeEntry.name);
      if (currentIndex === -1) return;
      const target = filmstrip[(currentIndex + step + filmstrip.length) % filmstrip.length];
      if (target) switchEntry(target);
    };

    useEffect(() => {
      const keyHandler = (e) => {
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          switchRelative(1);
        } else if (e.key === 'ArrowLeft') {
          e.preventDefault();
          switchRelative(-1);
        } else if ((e.key === '+' || e.key === '=') && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          zoom(1.15);
        } else if ((e.key === '-' || e.key === '_') && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          zoom(0.85);
        }
      };
      window.addEventListener('keydown', keyHandler);
      return () => window.removeEventListener('keydown', keyHandler);
    });

    const onWheel = (e) => {
      e.preventDefault();
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      const cx = e.clientX - rect.left - rect.width / 2;
      const cy = e.clientY - rect.top - rect.height / 2;
      setScale(prev => {
        const factor = e.deltaY < 0 ? 1.12 : 0.88;
        const next = clamp(prev * factor, 0.08, 10);
        const ratio = next / prev;
        setOffset(off => ({ x: off.x - cx * (ratio - 1), y: off.y - cy * (ratio - 1) }));
        transitionRef.current = true;
        window.setTimeout(() => { transitionRef.current = false; }, 120);
        return next;
      });
    };

    const onMouseDown = (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      setIsDragging(true);
      dragPointRef.current = { x: e.clientX, y: e.clientY };
    };

    const onMouseMove = (e) => {
      if (!isDragging || !dragPointRef.current) return;
      e.preventDefault();
      const dx = e.clientX - dragPointRef.current.x;
      const dy = e.clientY - dragPointRef.current.y;
      dragPointRef.current = { x: e.clientX, y: e.clientY };
      setOffset(off => ({ x: off.x + dx, y: off.y + dy }));
    };

    const stopDragging = () => {
      setIsDragging(false);
      dragPointRef.current = null;
    };

    const dist = (t1, t2) => Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);

    const onTouchStart = (e) => {
      if (e.touches.length === 1) {
        const t = e.touches[0];
        dragPointRef.current = { x: t.clientX, y: t.clientY };
      } else if (e.touches.length === 2) {
        pinchDistanceRef.current = dist(e.touches[0], e.touches[1]);
      }
    };

    const onTouchMove = (e) => {
      if (e.touches.length === 1 && dragPointRef.current) {
        const t = e.touches[0];
        const dx = t.clientX - dragPointRef.current.x;
        const dy = t.clientY - dragPointRef.current.y;
        dragPointRef.current = { x: t.clientX, y: t.clientY };
        setOffset(off => ({ x: off.x + dx, y: off.y + dy }));
      } else if (e.touches.length === 2 && pinchDistanceRef.current) {
        const dNow = dist(e.touches[0], e.touches[1]);
        const ratio = dNow / pinchDistanceRef.current;
        pinchDistanceRef.current = dNow;
        setScale(prev => clamp(prev * ratio, 0.08, 10));
      }
    };

    const onTouchEnd = () => {
      pinchDistanceRef.current = null;
      dragPointRef.current = null;
    };

    const onDoubleClick = (e) => {
      e.preventDefault();
      const next = scale > 1.4 ? 1 : 2.2;
      const container = containerRef.current;
      if (!container) {
        setScale(next);
        return;
      }
      const rect = container.getBoundingClientRect();
      const cx = e.clientX - rect.left - rect.width / 2;
      const cy = e.clientY - rect.top - rect.height / 2;
      const ratio = next / scale;
      setScale(next);
      setOffset(off => ({ x: off.x - cx * (ratio - 1), y: off.y - cy * (ratio - 1) }));
    };

    const handleImageLoaded = () => {
      const img = imageRef.current;
      if (!img) return;
      const stats = computeImageStats(img);
      setHistogram(stats.histogram);
      setDominantColor(stats.dominantColor);
    };

    const scaleLabel = `${(scale * 100).toFixed(scale >= 1 ? 0 : 1)}%`;

    const imageStyle = {
      maxWidth: '100%',
      maxHeight: '100%',
      transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale}) rotate(${rotate}deg)`,
      transition: transitionRef.current ? 'transform 0.18s cubic-bezier(.4,.8,.4,1)' : undefined,
      cursor: isDragging ? 'grabbing' : scale > 1 ? 'grab' : 'zoom-in',
      willChange: 'transform',
    };

    const exif = (stat?.exif ?? {});
    const infoIconStyle = { fontSize: 15, color: 'rgba(255,255,255,0.62)' };
    const exifValue = (key) => {
      const value = exif[key];
      if (typeof value === 'string' || typeof value === 'number') return value;
      return null;
    };
    const focalLength = (() => {
      const v = parseNumberish(exifValue('37386') || exifValue('37377'));
      return v ? `${v.toFixed(1)} mm` : null;
    })();
    const aperture = (() => {
      const v = parseNumberish(exifValue('33437') || exifValue('37378'));
      return v ? `f/${v.toFixed(1)}` : null;
    })();
    const exposure = (() => {
      const v = parseNumberish(exifValue('33434'));
      if (!v) return null;
      if (v >= 1) return `${v.toFixed(1)} s`;
      const denom = Math.max(1, Math.round(1 / v));
      return `1/${denom}`;
    })();
    const isoValue = exifValue('34855') || exifValue('34864');
    const width = parseNumberish(exifValue('40962'));
    const height = parseNumberish(exifValue('40963'));
    const colorSpace = exifValue('40961');
    const cameraMake = exifValue('271');
    const cameraModel = exifValue('272');
    const lensModel = exifValue('42036');
    const captureTime = exifValue('36867') || exifValue('36868') || exifValue('306');

    const basicList = [
      { label: '文件名', value: activeEntry.name, icon: React.createElement(FileOutlined, { style: infoIconStyle }) },
      { label: '文件大小', value: humanFileSize(stat?.size), icon: React.createElement(DatabaseOutlined, { style: infoIconStyle }) },
      { label: '分辨率', value: width && height ? `${width} × ${height}` : null, icon: React.createElement(ExpandOutlined, { style: infoIconStyle }) },
      { label: '颜色空间', value: colorSpace || null, icon: React.createElement(BgColorsOutlined, { style: infoIconStyle }) },
      { label: '修改时间', value: stat?.mtime ? formatDateTime(stat.mtime) : null, icon: React.createElement(ClockCircleOutlined, { style: infoIconStyle }) },
      { label: '路径', value: typeof stat?.path === 'string' ? stat.path : activePath, icon: React.createElement(FolderOutlined, { style: infoIconStyle }) },
    ];

    const shootingList = [
      { label: '焦距', value: focalLength, icon: React.createElement(AimOutlined, { style: infoIconStyle }) },
      { label: '光圈', value: aperture, icon: React.createElement(BulbOutlined, { style: infoIconStyle }) },
      { label: '快门', value: exposure, icon: React.createElement(ThunderboltOutlined, { style: infoIconStyle }) },
      { label: 'ISO', value: isoValue != null ? String(isoValue) : null, icon: React.createElement(AlertOutlined, { style: infoIconStyle }) },
    ];

    const deviceList = [
      {
        label: '相机',
        value: cameraModel ? `${cameraMake ? `${cameraMake} ` : ''}${cameraModel}` : (cameraMake || null),
        icon: React.createElement(CameraOutlined, { style: infoIconStyle }),
      },
      { label: '镜头', value: lensModel || null, icon: React.createElement(ApiOutlined, { style: infoIconStyle }) },
    ];

    const miscList = [
      { label: '拍摄时间', value: captureTime, icon: React.createElement(FieldTimeOutlined, { style: infoIconStyle }) },
    ];

    const controlsNode = React.createElement(ViewerControls, {
      style: controlsStyle,
      onPrev: () => switchRelative(-1),
      onNext: () => switchRelative(1),
      onZoomIn: () => zoom(1.18),
      onZoomOut: () => zoom(0.82),
      onRotate: rotateImage,
      onReset: resetView,
      onFit: fitToScreen,
      disableSwitch: filmstrip.length <= 1,
    });

    return React.createElement('div', { style: containerStyle },
      React.createElement('section', { style: viewerStyles.main },
        React.createElement('div', { style: mainBackdropStyle }),
        React.createElement('div', { style: viewerStyles.mainContent },
          React.createElement('div', {
            ref: containerRef,
            style: viewerStyle,
            onWheel,
            onMouseDown,
            onMouseMove,
            onMouseLeave: stopDragging,
            onMouseUp: stopDragging,
            onDoubleClick,
            onTouchStart,
            onTouchMove,
            onTouchEnd,
          },
            React.createElement('div', { style: viewerStyles.viewerCloseWrap },
              React.createElement(Tooltip, { title: '关闭' },
                React.createElement(Button, {
                  type: 'text',
                  icon: React.createElement(CloseOutlined),
                  onClick: host.close,
                  style: viewerStyles.viewerClose,
                })
              )
            ),
            loading
              ? React.createElement(Spin, { tip: '加载中' })
              : error
                ? React.createElement(Typography.Text, { type: 'danger' }, error)
                : imageUrl
                  ? React.createElement('img', {
                      ref: imageRef,
                      src: imageUrl,
                      alt: activeEntry.name,
                      onLoad: handleImageLoaded,
                      draggable: false,
                      crossOrigin: 'anonymous',
                      style: imageStyle,
                    })
                  : React.createElement(Typography.Text, null, '无可用内容'),
            React.createElement('div', { style: viewerStyles.scaleBadge }, scaleLabel),
            controlsNode
          ),
          React.createElement(Filmstrip, {
            shellStyle: filmstripShellStyle,
            listStyle: viewerStyles.filmstrip,
            entries: filmstrip,
            activeEntry,
            onSelect: switchEntry,
            filmstripRefs,
            pageInfo,
            getThumbUrl,
          })
        )
      ),
      React.createElement(InfoPanel, {
        style: sidePanelStyle,
        histogramCardStyle,
        title: activeEntry.name,
        captureTime: captureTime || null,
        basicList,
        shootingList,
        deviceList,
        miscList,
        histogram,
      })
    );
  }

  // 注册插件
  window.FoxelRegister({
    mount: (container, ctx) => {
      const root = ReactDOM.createRoot(container);
      root.render(React.createElement(ImageViewerApp, ctx));
      return () => root.unmount();
    },
  });
})();

