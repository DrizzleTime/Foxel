/**
 * 工具函数模块
 */
import type { VfsEntry, ExplorerSnapshot } from './foxel-types';
import type { RGB, Histogram, ImageStats } from './type';

export const DEFAULT_TONE: RGB = { r: 28, g: 32, b: 46 };

/**
 * 判断是否为图片文件
 */
export const isImageEntry = (ent: VfsEntry): boolean => {
  if (ent.is_dir) return false;
  if (typeof ent.has_thumbnail === 'boolean' && ent.has_thumbnail) return true;
  const ext = ent.name.split('.').pop()?.toLowerCase();
  if (!ext) return false;
  return ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'avif', 'ico', 'tif', 'tiff', 'svg', 'heic', 'heif', 'arw', 'cr2', 'cr3', 'nef', 'rw2', 'orf', 'pef', 'dng'].includes(ext);
};

/**
 * 构建缩略图 URL
 */
export const buildThumbUrl = (baseUrl: string, fullPath: string, w = 180, h = 120): string => {
  const base = baseUrl.replace(/\/+$/, '');
  const clean = fullPath.replace(/^\/+/, '');
  return `${base}/fs/thumb/${encodeURI(clean)}?w=${w}&h=${h}&fit=cover`;
};

/**
 * 获取目录路径
 */
export const getDirectory = (fullPath: string): string => {
  const path = fullPath.startsWith('/') ? fullPath : `/${fullPath}`;
  const idx = path.lastIndexOf('/');
  if (idx <= 0) return '/';
  return path.slice(0, idx) || '/';
};

/**
 * 拼接路径
 */
export const joinPath = (dir: string, name: string): string => {
  if (dir === '/' || dir === '') return `/${name}`;
  return `${dir.replace(/\/$/, '')}/${name}`;
};

/**
 * 限制数值范围
 */
export const clamp = (value: number, min: number, max: number): number => 
  Math.max(min, Math.min(max, value));

/**
 * 解析数字或分数字符串
 */
export const parseNumberish = (raw: string | number | undefined): number | null => {
  if (typeof raw === 'number') return raw;
  if (typeof raw !== 'string') return null;
  if (raw.includes('/')) {
    const [a, b] = raw.split('/').map(v => Number(v));
    if (!Number.isNaN(a) && !Number.isNaN(b) && b !== 0) return a / b;
  }
  const val = Number(raw);
  return Number.isNaN(val) ? null : val;
};

/**
 * 格式化文件大小
 */
export const humanFileSize = (size: number | undefined): string => {
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

/**
 * 读取文件浏览器快照
 */
export const readExplorerSnapshot = (dir: string): ExplorerSnapshot | null => {
  if (typeof window === 'undefined') return null;
  const snap = window.__FOXEL_LAST_EXPLORER_PAGE__;
  if (!snap) return null;
  const snapshotPath = snap.path === '' ? '/' : snap.path;
  const normalizedSnap = snapshotPath.endsWith('/') && snapshotPath !== '/' 
    ? snapshotPath.slice(0, -1) 
    : snapshotPath;
  const normalizedTarget = dir.endsWith('/') && dir !== '/' 
    ? dir.slice(0, -1) 
    : dir;
  if (normalizedSnap !== normalizedTarget) return null;
  return snap;
};

/**
 * 格式化日期时间
 */
export const formatDateTime = (ts: number | undefined): string => {
  if (!ts) return '-';
  try {
    return new Date(ts * 1000).toLocaleString();
  } catch {
    return '-';
  }
};

/**
 * 限制颜色通道值
 */
export const clampChannel = (value: number): number => 
  Math.max(0, Math.min(255, value));

/**
 * 混合颜色
 */
export const mixColor = (base: RGB, target: RGB, ratio: number): RGB => ({
  r: clampChannel(base.r * (1 - ratio) + target.r * ratio),
  g: clampChannel(base.g * (1 - ratio) + target.g * ratio),
  b: clampChannel(base.b * (1 - ratio) + target.b * ratio),
});

/**
 * RGB 转 RGBA 字符串
 */
export const rgbToRgba = (color: RGB, alpha: number): string => 
  `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${alpha})`;

/**
 * 计算图片统计信息（直方图和主色调）
 */
export const computeImageStats = (img: HTMLImageElement): ImageStats => {
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
    
    const histogram: Histogram = { r, g, b };
    if (count === 0) return { histogram, dominantColor: null };
    
    const dominantColor: RGB = {
      r: rTotal / count,
      g: gTotal / count,
      b: bTotal / count,
    };
    
    return { histogram, dominantColor };
  } catch {
    return { histogram: null, dominantColor: null };
  }
};
