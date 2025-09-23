import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
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
} from '@ant-design/icons';
import { API_BASE_URL, vfsApi, type VfsEntry } from '../../api/client';
import type { AppComponentProps } from '../types';
import { ImageCanvas } from './components/ImageCanvas';
import { ViewerControls } from './components/ViewerControls';
import { Filmstrip } from './components/Filmstrip';
import { InfoPanel } from './components/InfoPanel';
import type { HistogramData, RgbColor, InfoItem } from './components/types';
import { viewerStyles } from './styles';

interface ExplorerSnapshot {
  path: string;
  entries: VfsEntry[];
  pagination?: { page: number; page_size: number; total: number };
  sortBy?: string;
  sortOrder?: string;
  timestamp: number;
}

interface FileStat {
  name?: string;
  is_dir?: boolean;
  size?: number;
  mtime?: number;
  mode?: number;
  path?: string;
  type?: string;
  exif?: Record<string, unknown>;
}

declare global {
  interface WindowEventMap {
    'foxel:file-explorer-page': CustomEvent<ExplorerSnapshot>;
  }
}
type ExplorerAwareWindow = Window & { __FOXEL_LAST_EXPLORER_PAGE__?: ExplorerSnapshot };

const DEFAULT_TONE: RgbColor = { r: 28, g: 32, b: 46 };

const isImageEntry = (ent: VfsEntry) => {
  if (ent.is_dir) return false;
  const maybe = ent as VfsEntry & { is_image?: boolean };
  if (typeof maybe.is_image === 'boolean' && maybe.is_image) return true;
  const ext = ent.name.split('.').pop()?.toLowerCase();
  if (!ext) return false;
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'ico', 'tif', 'tiff', 'svg', 'heic', 'heif', 'arw', 'cr2', 'cr3', 'nef', 'rw2', 'orf', 'pef', 'dng'].includes(ext);
};

const buildThumbUrl = (fullPath: string, w = 180, h = 120) => {
  const base = API_BASE_URL.replace(/\/+$/, '');
  const clean = fullPath.replace(/^\/+/, '');
  return `${base}/fs/thumb/${encodeURI(clean)}?w=${w}&h=${h}&fit=cover`;
};

const getDirectory = (fullPath: string) => {
  const path = fullPath.startsWith('/') ? fullPath : `/${fullPath}`;
  const idx = path.lastIndexOf('/');
  if (idx <= 0) return '/';
  return path.slice(0, idx) || '/';
};

const joinPath = (dir: string, name: string) => {
  if (dir === '/' || dir === '') return `/${name}`;
  return `${dir.replace(/\/$/, '')}/${name}`;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

const parseNumberish = (raw: unknown): number | null => {
  if (typeof raw === 'number') return raw;
  if (typeof raw !== 'string') return null;
  if (raw.includes('/')) {
    const [a, b] = raw.split('/').map(v => Number(v));
    if (!Number.isNaN(a) && !Number.isNaN(b) && b !== 0) return a / b;
  }
  const val = Number(raw);
  return Number.isNaN(val) ? null : val;
};

const humanFileSize = (size: number | undefined) => {
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

const readExplorerSnapshot = (dir: string): ExplorerSnapshot | null => {
  if (typeof window === 'undefined') return null;
  const snap = (window as ExplorerAwareWindow).__FOXEL_LAST_EXPLORER_PAGE__;
  if (!snap) return null;
  const snapshotPath = snap.path === '' ? '/' : snap.path;
  const normalizedSnap = snapshotPath.endsWith('/') && snapshotPath !== '/' ? snapshotPath.slice(0, -1) : snapshotPath;
  const normalizedTarget = dir.endsWith('/') && dir !== '/' ? dir.slice(0, -1) : dir;
  if (normalizedSnap !== normalizedTarget) return null;
  return snap;
};

const formatDateTime = (ts?: number) => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return '-';
  }
};

const clampChannel = (value: number) => Math.max(0, Math.min(255, value));

const mixColor = (base: RgbColor, target: RgbColor, ratio: number): RgbColor => ({
  r: clampChannel(base.r * (1 - ratio) + target.r * ratio),
  g: clampChannel(base.g * (1 - ratio) + target.g * ratio),
  b: clampChannel(base.b * (1 - ratio) + target.b * ratio),
});

const rgbToRgba = (color: RgbColor, alpha: number) => `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${alpha})`;

const computeImageStats = (img: HTMLImageElement): { histogram: HistogramData | null; dominantColor: RgbColor | null } => {
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
    const histogram: HistogramData = { r, g, b };
    if (count === 0) return { histogram, dominantColor: null };
    const dominantColor: RgbColor = {
      r: rTotal / count,
      g: gTotal / count,
      b: bTotal / count,
    };
    return { histogram, dominantColor };
  } catch {
    return { histogram: null, dominantColor: null };
  }
};

export const ImageViewerApp: React.FC<AppComponentProps> = ({ filePath, entry, onRequestClose }) => {
  const normalizedInitialPath = filePath.startsWith('/') ? filePath : `/${filePath}`;
  const [activeEntry, setActiveEntry] = useState<VfsEntry>(entry);
  const [activePath, setActivePath] = useState<string>(normalizedInitialPath);
  const [imageUrl, setImageUrl] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [stat, setStat] = useState<FileStat | null>(null);
  const [histogram, setHistogram] = useState<HistogramData | null>(null);
  const [dominantColor, setDominantColor] = useState<RgbColor | null>(null);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [rotate, setRotate] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [filmstrip, setFilmstrip] = useState<VfsEntry[]>([]);
  const [pageInfo, setPageInfo] = useState<{ page: number; total: number; pageSize: number } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const dragPointRef = useRef<{ x: number; y: number } | null>(null);
  const pinchDistanceRef = useRef<number | null>(null);
  const transitionRef = useRef(false);
  const filmstripRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const directory = useMemo(() => getDirectory(activePath), [activePath]);

  const baseTone = useMemo<RgbColor>(() => dominantColor ?? DEFAULT_TONE, [dominantColor]);

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

  const getThumbUrl = useCallback((item: VfsEntry) => {
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
      vfsApi.getTempLinkToken(cleaned),
      vfsApi.stat(activePath) as Promise<FileStat>,
    ])
      .then(([token, metadata]) => {
        if (cancelled) return;
        setImageUrl(vfsApi.getTempPublicUrl(token.token));
        setStat(metadata);
        setScale(1);
        setRotate(0);
        setOffset({ x: 0, y: 0 });
      })
      .catch((err: unknown) => {
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

  const refreshFilmstrip = useCallback((dir: string) => {
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

  useEffect(() => {
    const keyHandler = (e: KeyboardEvent) => {
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

  const zoom = useCallback((factor: number) => {
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

  const onWheel = (e: React.WheelEvent) => {
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

  const onMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    e.preventDefault();
    setIsDragging(true);
    dragPointRef.current = { x: e.clientX, y: e.clientY };
  };

  const onMouseMove = (e: React.MouseEvent) => {
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

  const dist = (t1: React.Touch, t2: React.Touch) => Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY);

  const onTouchStart = (e: React.TouchEvent) => {
    if (e.touches.length === 1) {
      const t = e.touches[0];
      dragPointRef.current = { x: t.clientX, y: t.clientY };
    } else if (e.touches.length === 2) {
      pinchDistanceRef.current = dist(e.touches[0], e.touches[1]);
    }
  };

  const onTouchMove = (e: React.TouchEvent) => {
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

  const onDoubleClick = (e: React.MouseEvent) => {
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

  const switchEntry = (target: VfsEntry) => {
    const nextPath = joinPath(directory, target.name);
    setActiveEntry(target);
    setActivePath(nextPath);
  };

  const switchRelative = (step: number) => {
    if (filmstrip.length <= 1) return;
    const currentIndex = filmstrip.findIndex(item => item.name === activeEntry.name);
    if (currentIndex === -1) return;
    const target = filmstrip[(currentIndex + step + filmstrip.length) % filmstrip.length];
    if (target) switchEntry(target);
  };

  const scaleLabel = `${(scale * 100).toFixed(scale >= 1 ? 0 : 1)}%`;

  const imageStyle: React.CSSProperties = {
    maxWidth: '100%',
    maxHeight: '100%',
    transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale}) rotate(${rotate}deg)`,
    transition: transitionRef.current ? 'transform 0.18s cubic-bezier(.4,.8,.4,1)' : undefined,
    cursor: isDragging ? 'grabbing' : scale > 1 ? 'grab' : 'zoom-in',
    willChange: 'transform',
  };

  const controlsNode = (
    <ViewerControls
      style={controlsStyle}
      onPrev={() => switchRelative(-1)}
      onNext={() => switchRelative(1)}
      onZoomIn={() => zoom(1.18)}
      onZoomOut={() => zoom(0.82)}
      onRotate={rotateImage}
      onReset={resetView}
      onFit={fitToScreen}
      disableSwitch={filmstrip.length <= 1}
    />
  );

  const exif = (stat?.exif ?? {}) as Record<string, unknown>;
  const infoIconStyle: React.CSSProperties = { fontSize: 15, color: 'rgba(255,255,255,0.62)' };
  const exifValue = (key: string): string | number | null => {
    const value = exif[key];
    if (typeof value === 'string' || typeof value === 'number') return value;
    return null;
  };
  const focalLength = (() => {
    const v = parseNumberish(exifValue('37386') ?? exifValue('37377'));
    return v ? `${v.toFixed(1)} mm` : null;
  })();
  const aperture = (() => {
    const v = parseNumberish(exifValue('33437') ?? exifValue('37378'));
    return v ? `f/${v.toFixed(1)}` : null;
  })();
  const exposure = (() => {
    const v = parseNumberish(exifValue('33434'));
    if (!v) return null;
    if (v >= 1) return `${v.toFixed(1)} s`;
    const denom = Math.max(1, Math.round(1 / v));
    return `1/${denom}`;
  })();
  const isoValue = exifValue('34855') ?? exifValue('34864');
  const width = parseNumberish(exifValue('40962'));
  const height = parseNumberish(exifValue('40963'));
  const colorSpace = exifValue('40961');
  const cameraMake = exifValue('271');
  const cameraModel = exifValue('272');
  const lensModel = exifValue('42036');
  const captureTime = exifValue('36867') ?? exifValue('36868') ?? exifValue('306');

  const basicList: InfoItem[] = [
    { label: '文件名', value: activeEntry.name, icon: <FileOutlined style={infoIconStyle} /> },
    { label: '文件大小', value: humanFileSize(stat?.size), icon: <DatabaseOutlined style={infoIconStyle} /> },
    { label: '分辨率', value: width && height ? `${width} × ${height}` : null, icon: <ExpandOutlined style={infoIconStyle} /> },
    { label: '颜色空间', value: colorSpace ?? null, icon: <BgColorsOutlined style={infoIconStyle} /> },
    { label: '修改时间', value: stat?.mtime ? formatDateTime(stat.mtime) : null, icon: <ClockCircleOutlined style={infoIconStyle} /> },
    { label: '路径', value: typeof stat?.path === 'string' ? stat.path : activePath, icon: <FolderOutlined style={infoIconStyle} /> },
  ];

  const shootingList: InfoItem[] = [
    { label: '焦距', value: focalLength, icon: <AimOutlined style={infoIconStyle} /> },
    { label: '光圈', value: aperture, icon: <BulbOutlined style={infoIconStyle} /> },
    { label: '快门', value: exposure, icon: <ThunderboltOutlined style={infoIconStyle} /> },
    { label: 'ISO', value: isoValue != null ? isoValue.toString() : null, icon: <AlertOutlined style={infoIconStyle} /> },
  ];

  const deviceList: InfoItem[] = [
    {
      label: '相机',
      value: cameraModel ? `${cameraMake ? `${cameraMake} ` : ''}${cameraModel}` : (cameraMake ?? null),
      icon: <CameraOutlined style={infoIconStyle} />,
    },
    { label: '镜头', value: lensModel ?? null, icon: <ApiOutlined style={infoIconStyle} /> },
  ];

  const miscList: InfoItem[] = [
    { label: '拍摄时间', value: captureTime, icon: <FieldTimeOutlined style={infoIconStyle} /> },
  ];

  return (
    <div style={containerStyle}>
      <section style={viewerStyles.main}>
        <div style={mainBackdropStyle} />
        <div style={viewerStyles.mainContent}>
          <ImageCanvas
            containerRef={containerRef}
            imageRef={imageRef}
            viewerStyle={viewerStyle}
            controls={controlsNode}
            scaleLabel={scaleLabel}
            imageStyle={imageStyle}
            loading={loading}
            error={error}
            imageUrl={imageUrl}
            activeEntry={activeEntry}
            onRequestClose={onRequestClose}
            onImageLoad={handleImageLoaded}
            onWheel={onWheel}
            onMouseDown={onMouseDown}
            onMouseMove={onMouseMove}
            onMouseLeave={stopDragging}
            onMouseUp={stopDragging}
            onDoubleClick={onDoubleClick}
            onTouchStart={onTouchStart}
            onTouchMove={onTouchMove}
            onTouchEnd={onTouchEnd}
          />

          <Filmstrip
            shellStyle={filmstripShellStyle}
            listStyle={viewerStyles.filmstrip}
            entries={filmstrip}
            activeEntry={activeEntry}
            onSelect={switchEntry}
            filmstripRefs={filmstripRefs}
            pageInfo={pageInfo}
            getThumbUrl={getThumbUrl}
          />
        </div>
      </section>

      <InfoPanel
        style={sidePanelStyle}
        histogramCardStyle={histogramCardStyle}
        title={activeEntry.name}
        captureTime={captureTime ?? null}
        basicList={basicList}
        shootingList={shootingList}
        deviceList={deviceList}
        miscList={miscList}
        histogram={histogram}
      />
    </div>
  );
};
