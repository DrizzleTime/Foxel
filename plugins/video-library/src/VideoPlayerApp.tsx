/**
 * 视频播放器组件
 */
import React, { useRef, useEffect } from 'react';
import type { PluginContext } from './foxel-types';

export const VideoPlayerApp: React.FC<PluginContext> = ({ urls }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
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

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%', backgroundColor: '#000' }}
    />
  );
};

