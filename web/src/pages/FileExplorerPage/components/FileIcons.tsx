import React from 'react';
import { 
  FileOutlined,
  FileImageOutlined,
  VideoCameraOutlined,
  AudioOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FilePptOutlined,
  FileZipOutlined,
  CodeOutlined,
  FileMarkdownOutlined,
  SettingOutlined,
  DatabaseOutlined,
  FontSizeOutlined,
} from '@ant-design/icons';

const lightenColor = (hex: string, amount: number) => {
  const s = hex.replace('#', '');
  const n = s.length === 3 ? s.split('').map(c => c + c).join('') : s;
  const num = parseInt(n, 16);
  if (Number.isNaN(num) || n.length !== 6) return hex;
  const r = (num >> 16) & 255;
  const g = (num >> 8) & 255;
  const b = num & 255;
  const mix = (c: number) => Math.round(c + (255 - c) * amount);
  const toHex = (v: number) => v.toString(16).padStart(2, '0');
  return `#${toHex(mix(r))}${toHex(mix(g))}${toHex(mix(b))}`;
};

export const getFileIcon = (fileName: string, size: number = 16, resolvedMode: 'light' | 'dark' | 'system' = 'light') => {
  const ext = fileName.split('.').pop()?.toLowerCase() || '';
  const iconStyle: React.CSSProperties = { fontSize: size, marginRight: size === 16 ? 6 : 0 };

  const adj = (color: string) => (resolvedMode === 'dark' ? lightenColor(color, 0.3) : color);
  const make = (node: React.ReactNode, color: string) => React.cloneElement(node as any, { style: { ...iconStyle, color: adj(color) } });

  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'tiff'].includes(ext)) return make(<FileImageOutlined />, '#52c41a');
  if (['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm', 'm4v', '3gp'].includes(ext)) return make(<VideoCameraOutlined />, '#fa541c');
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a'].includes(ext)) return make(<AudioOutlined />, '#722ed1');
  if (['pdf'].includes(ext)) return make(<FilePdfOutlined />, '#f5222d');
  if (['doc', 'docx'].includes(ext)) return make(<FileWordOutlined />, '#1890ff');
  if (['xls', 'xlsx'].includes(ext)) return make(<FileExcelOutlined />, '#52c41a');
  if (['ppt', 'pptx'].includes(ext)) return make(<FilePptOutlined />, '#fa8c16');
  if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz'].includes(ext)) return make(<FileZipOutlined />, '#faad14');
  if (['js','jsx','ts','tsx','vue','html','htm','css','scss','sass','less','json','xml','yaml','yml','py','java','cpp','cc','cxx','c','h','hpp','hxx','php','rb','go','rs','rust','swift','kt','scala','clj','cljs','cs','vb','fs','pl','pm','r','lua','dart','elm'].includes(ext)) return make(<CodeOutlined />, '#13c2c2');
  if (['md', 'markdown'].includes(ext)) return make(<FileMarkdownOutlined />, '#1890ff');
  if (['txt', 'log', 'ini', 'cfg', 'conf', 'sh', 'bash', 'zsh', 'fish', 'ps1', 'bat', 'cmd', 'dockerfile', 'makefile', 'gradle', 'cmake', 'gitignore', 'gitattributes', 'editorconfig', 'prettierrc'].includes(ext)) return make(<FileTextOutlined />, '#8c8c8c');
  if (['ttf', 'otf', 'woff', 'woff2', 'eot'].includes(ext)) return make(<FontSizeOutlined />, '#eb2f96');
  if (['db', 'sqlite', 'sql'].includes(ext)) return make(<DatabaseOutlined />, '#fa541c');
  if (['env', 'config', 'properties', 'toml'].includes(ext)) return make(<SettingOutlined />, '#faad14');
  return make(<FileOutlined />, '#8c8c8c');
};
