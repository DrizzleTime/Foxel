import type { AppDescriptor } from '../types';
import { PdfViewerApp } from './PdfViewer';

const supportedExts = ['pdf'];

export const descriptor: AppDescriptor = {
  key: 'pdf-viewer',
  name: 'PDF 查看器',
  iconUrl: 'https://api.iconify.design/mdi:file-pdf-box.svg',
  description: '内置 PDF 查看器。',
  author: 'Foxel',
  supportedExts,
  supported: (entry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    return supportedExts.includes(ext);
  },
  component: PdfViewerApp,
  default: true,
  defaultBounds: { width: 1024, height: 768, x: 160, y: 100 },
};
