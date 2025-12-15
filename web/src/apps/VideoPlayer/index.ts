import type { AppDescriptor } from '../types';
import { VideoPlayerApp } from './VideoPlayer.tsx';
import { VideoLibraryApp } from './VideoLibrary.tsx';

const supportedExts = ['mp4','webm','ogg','m4v','mov','mkv','avi','wmv','flv','3gp'];

export const descriptor: AppDescriptor = {
  key: 'video-player',
  name: '视频播放器',
  iconUrl: 'https://api.iconify.design/mdi:video.svg',
  description: '内置视频播放器，支持常见视频格式播放。',
  author: 'Foxel',
  openAppComponent: VideoLibraryApp,
  supportedExts,
  supported: (entry) => {
    if (entry.is_dir) return false;
    const ext = entry.name.split('.').pop()?.toLowerCase() || '';
    return supportedExts.includes(ext);
  },
  component: VideoPlayerApp,
  default: true,
  defaultBounds: { width: 960, height: 600, x: 180, y: 120 }
};
