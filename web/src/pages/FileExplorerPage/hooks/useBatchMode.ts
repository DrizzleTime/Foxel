import { useCallback, useMemo, useState } from 'react';
import type { VfsEntry } from '../../../api/client';

export interface BatchItem {
  /** Full path of the selected entry, e.g. /docs/report.pdf */
  path: string;
  name: string;
  isDir: boolean;
  size: number;
  mtime: number;
}

export function joinPath(base: string, name: string): string {
  return ((base === '/' ? '' : base) + '/' + name).replace(/\/+/g, '/');
}

export function useBatchMode(currentPath: string) {
  const [active, setActive] = useState(false);
  const [items, setItems] = useState<BatchItem[]>([]);

  const exit = useCallback(() => {
    setActive(false);
    setItems([]);
  }, []);

  const enter = useCallback(() => setActive(true), []);

  const toBatchItem = useCallback((entry: VfsEntry): BatchItem => ({
    path: joinPath(currentPath, entry.name),
    name: entry.name,
    isDir: entry.is_dir,
    size: entry.size,
    mtime: entry.mtime,
  }), [currentPath]);

  /** Toggle one entry (ignore mount points — they cannot be moved/deleted). */
  const toggle = useCallback((entry: VfsEntry) => {
    if (entry.type === 'mount') return;
    const next = toBatchItem(entry);
    setItems(prev => prev.some(i => i.path === next.path)
      ? prev.filter(i => i.path !== next.path)
      : [...prev, next]);
  }, [toBatchItem]);

  /** Toggle a whole directory listing (used by select-all). Additive across directories. */
  const toggleMany = useCallback((entries: VfsEntry[]) => {
    setItems(prev => {
      const next = new Map(prev.map(i => [i.path, i]));
      const candidates = entries.filter(e => e.type !== 'mount').map(toBatchItem);
      const allSelected = candidates.every(c => next.has(c.path));
      if (allSelected) {
        candidates.forEach(c => next.delete(c.path));
      } else {
        candidates.forEach(c => next.set(c.path, c));
      }
      return [...next.values()];
    });
  }, [toBatchItem]);

  const clear = useCallback(() => setItems([]), []);

  const removePaths = useCallback((paths: string[]) => {
    const removed = new Set(paths);
    setItems(prev => prev.filter(item => !removed.has(item.path)));
  }, []);

  const selectedPaths = useMemo(() => items.map(i => i.path), [items]);

  /** Names selected within the current directory (for rendering check circles). */
  const currentDirNames = useMemo(() => {
    const names = new Set<string>();
    for (const item of items) {
      const parent = item.path.slice(0, item.path.lastIndexOf('/')) || '/';
      if (parent === currentPath) names.add(item.name);
    }
    return names;
  }, [items, currentPath]);

  return {
    active, setActive, enter, exit,
    items, setItems, toBatchItem,
    toggle, toggleMany, clear, removePaths,
    selectedPaths, currentDirNames,
    count: items.length,
  };
}
