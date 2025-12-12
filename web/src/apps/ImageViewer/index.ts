import type { AppDescriptor } from '../types';
import { ImageViewerApp } from './ImageViewer.tsx';

const supportedExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif', 'arw', 'cr2', 'cr3', 'nef', 'rw2', 'orf', 'pef', 'dng'];

export const descriptor: AppDescriptor = {
  key: 'image-viewer',
  name: '图片查看器',
  iconUrl: 'https://api.iconify.design/mdi:image.svg',
  description: '内置图片查看器，支持常见图片与部分 RAW 格式预览。',
  author: 'Foxel',
  supportedExts,
  supported: (entry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    return supportedExts.includes(ext);
  },
  component: ImageViewerApp,
  default: true,
  defaultMaximized:true,
  useSystemWindow:false,
  defaultBounds: { width: 820, height: 620, x: 140, y: 96 }
};
