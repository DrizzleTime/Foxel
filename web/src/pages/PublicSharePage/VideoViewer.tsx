import React, { useEffect, useRef } from 'react';
import Artplayer from 'artplayer';
import { shareApi } from '../../api/share';
import type { VfsEntry } from '../../api/vfs';

interface VideoViewerProps {
  token: string;
  entry: VfsEntry;
  password?: string;
  path: string;
}

export const VideoViewer: React.FC<VideoViewerProps> = ({ token, entry, password, path }) => {
  const artRef = useRef<HTMLDivElement | null>(null);
  const artInstance = useRef<Artplayer | null>(null);

  useEffect(() => {
    const videoUrl = shareApi.downloadUrl(token, path, password);

    if (artRef.current) {
      artInstance.current = new Artplayer({
        container: artRef.current,
        url: videoUrl,
        autoplay: true,
        fullscreen: true,
        fullscreenWeb: true,
        pip: true,
        setting: true,
        playbackRate: true,
      });
    }

    return () => {
      if (artInstance.current) {
        artInstance.current.destroy();
      }
    };
  }, [token, entry.name, password, path]);

  return (
    <div
      ref={artRef}
      style={{
        width: '100%',
        height: '450px',
        backgroundColor: '#000'
      }}
    />
  );
};