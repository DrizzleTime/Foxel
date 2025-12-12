import type { AppDescriptor } from '../types';
import { OfficeViewerApp } from './OfficeViewer.tsx';

const supportedExts = ['docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt'];

export const descriptor: AppDescriptor = {
  key: 'office-viewer',
  name: 'Office 文档查看器',
  iconUrl: 'https://api.iconify.design/mdi:file-word-box.svg',
  description: '内置 Office 文档查看器，支持 Word/Excel/PowerPoint 文件预览。',
  author: 'Foxel',
  supportedExts,
  supported: (entry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    return supportedExts.includes(ext);
  },
  component: OfficeViewerApp,
  default: true,
  defaultBounds: { width: 1024, height: 768, x: 150, y: 100 }
};
