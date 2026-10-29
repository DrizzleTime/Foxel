import { useMemo } from 'react';
import type { VfsEntry } from '../../../api/client';
import { API_BASE_URL } from '../../../api/client';

const buildThumbUrl = (filePath: string, w = 512, h = 512, fit = 'cover') => {
  const origin = API_BASE_URL.replace(/\/+$/, '');
  const cleanPath = filePath.replace(/^\/+/, '');
  return `${origin}/fs/thumb/${encodeURI(cleanPath)}?w=${w}&h=${h}&fit=${encodeURIComponent(fit)}`;
};

export function useThumbnails(entries: VfsEntry[], path: string) {
  const thumbs = useMemo(() => {
    const urls: Record<string, string> = {};
    for (const entry of entries) {
      if (!entry.is_dir && entry.has_thumbnail) {
        const fullPath = (path === '/' ? '' : path) + '/' + entry.name;
        urls[entry.name] = buildThumbUrl(fullPath);
      }
    }
    return urls;
  }, [entries, path]);

  return { thumbs };
}
