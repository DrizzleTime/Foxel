import type { AppDescriptor } from '../types';
import { TextEditorApp } from './TextEditor.tsx';

const supportedExts = [
  // Text formats
  'txt', 'md', 'markdown', 'log',
  // Data formats
  'json', 'yaml', 'yml', 'xml', 'toml', 'ini', 'cfg', 'conf',
  // Web technologies
  'html', 'htm', 'css', 'scss', 'sass', 'less', 'js', 'jsx', 'ts', 'tsx', 'vue',
  // Programming languages
  'py', 'java', 'c', 'cpp', 'cc', 'cxx', 'h', 'hpp', 'hxx',
  'php', 'rb', 'go', 'rs', 'swift', 'kt', 'scala', 'clj', 'cljs',
  'cs', 'vb', 'fs', 'pl', 'pm', 'r', 'lua', 'dart', 'elm',
  // Database
  'sql',
  // Shell and scripts
  'sh', 'bash', 'zsh', 'fish', 'ps1', 'bat', 'cmd',
  // Build and config files
  'dockerfile', 'makefile', 'gradle', 'cmake',
  // Other common text files
  'gitignore', 'gitattributes', 'editorconfig', 'prettierrc'
];

export const descriptor: AppDescriptor = {
  key: 'text-editor',
  name: '文本编辑器',
  iconUrl: 'https://api.iconify.design/mdi:file-document-outline.svg',
  description: '内置文本/代码编辑器，支持常见文本与代码格式。',
  author: 'Foxel',
  supportedExts,
  supported: (entry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    // Supports common text and code formats
    return supportedExts.includes(ext);
  },
  component: TextEditorApp,
  default: true,
  defaultBounds: { width: 1024, height: 768, x: 120, y: 80 }
};
