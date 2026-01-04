/**
 * 工具函数
 */

const TMDB_IMAGE_BASE = 'https://image.tmdb.org/t/p/';

export function tmdbImage(path: string | undefined, size: string): string | undefined {
  if (!path) return undefined;
  return `${TMDB_IMAGE_BASE}${size}${path}`;
}

