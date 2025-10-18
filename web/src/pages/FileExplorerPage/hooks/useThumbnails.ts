import { useState, useEffect } from 'react';
import type { VfsEntry } from '../../../api/client';
import { API_BASE_URL } from '../../../api/client';

const buildThumbUrl = (filePath: string, w = 256, h = 256, fit = 'cover') => {
  const origin = API_BASE_URL.replace(/\/+$/, '');
  const cleanPath = filePath.replace(/^\/+/, '');
  return `${origin}/fs/thumb/${encodeURI(cleanPath)}?w=${w}&h=${h}&fit=${encodeURIComponent(fit)}`;
};

export function useThumbnails(entries: VfsEntry[], path: string) {
  const [thumbs, setThumbs] = useState<Record<string, string>>({});

  useEffect(() => {
    const newThumbs: Record<string, string> = {};
    const targets = entries.filter(e => !e.is_dir && (e as any).has_thumbnail && !thumbs[e.name]);

    if (targets.length > 0) {
      targets.forEach(ent => {
        const fullPath = (path === '/' ? '' : path) + '/' + ent.name;
        newThumbs[ent.name] = buildThumbUrl(fullPath, 256, 256, 'cover');
      });
      setThumbs(prev => ({ ...prev, ...newThumbs }));
    }

    // Clean up old thumbs
    const currentEntryNames = new Set(entries.map(e => e.name));
    const toRemove = Object.keys(thumbs).filter(key => !currentEntryNames.has(key));

    if (toRemove.length > 0) {
      setThumbs(prev => {
        const next = { ...prev };
        toRemove.forEach(key => delete next[key]);
        return next;
      });
    }
  }, [entries, path, thumbs]);

  return { thumbs };
}
