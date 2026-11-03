import { useMemo } from 'react';
import type { VfsEntry } from '../../../api/client';
import { encodeFilePath } from '../../../api/transfers';

const buildThumbUrl = (filePath: string, w = 512, h = 512, fit = 'cover') => {
  const cleanPath = encodeFilePath(filePath);
  return `/fs/thumb/${cleanPath}?w=${w}&h=${h}&fit=${encodeURIComponent(fit)}`;
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
