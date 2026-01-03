import { message } from 'antd';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router';
import { vfsApi, type VfsEntry } from '../../../api/client';
import type { SearchResultItem } from '../../../api/vfs';
import { useI18n } from '../../../i18n';

export type SearchMode = 'vector' | 'filename';

export type SearchDisplayItem = {
  item: SearchResultItem;
  fullPath: string;
  dir: string;
  name: string;
};

const PAGE_SIZE = 10;

interface UseFileSearchParams {
  currentPath: string;
  navigateTo: (path: string) => void;
  openFileWithDefaultApp: (entry: VfsEntry, currentPath: string) => void;
  openContextMenu: (e: React.MouseEvent, entry: VfsEntry) => void;
  closeContextMenus: () => void;
  activeEntry?: VfsEntry | null;
}

export function useFileSearch({
  currentPath,
  navigateTo,
  openFileWithDefaultApp,
  openContextMenu,
  closeContextMenus,
  activeEntry,
}: UseFileSearchParams) {
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useI18n();

  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const query = (searchParams.get('q') || '').trim();
  const mode = (searchParams.get('mode') === 'filename' ? 'filename' : 'vector') as SearchMode;
  const page = Math.max(1, Number(searchParams.get('page') || '1') || 1);
  const isSearching = Boolean(query);

  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const requestIdRef = useRef(0);

  const entryCacheRef = useRef<Map<string, VfsEntry>>(new Map());
  const [entrySnapshot, setEntrySnapshot] = useState<Record<string, VfsEntry>>({});
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [actionPath, setActionPath] = useState<string>('/');

  const normalizeFullPath = useCallback((fullPath: string) => {
    const raw = (fullPath || '').replace(/\/+$/, '');
    if (!raw) return '/';
    const leading = raw.startsWith('/') ? raw : `/${raw}`;
    return leading.replace(/\/{2,}/g, '/');
  }, []);

  const splitPath = useCallback((fullPath: string) => {
    const normalized = normalizeFullPath(fullPath);
    const parts = normalized.split('/').filter(Boolean);
    const name = parts.pop() || '';
    const dir = parts.length > 0 ? `/${parts.join('/')}` : '/';
    return { fullPath: normalized, dir, name };
  }, [normalizeFullPath]);

  const runSearch = useCallback(async (requestId: number) => {
    try {
      const res = await vfsApi.searchFiles(
        query,
        mode === 'filename' ? PAGE_SIZE : 10,
        mode,
        mode === 'filename' ? page : undefined,
        mode === 'filename' ? PAGE_SIZE : undefined,
      );
      if (requestId !== requestIdRef.current) return;
      setResults(res.items || []);
      if (mode === 'filename') {
        setHasMore(Boolean(res.pagination?.has_more));
      } else {
        setHasMore(false);
      }
    } catch (e) {
      if (requestId !== requestIdRef.current) return;
      const msg = e instanceof Error ? e.message : t('Load failed');
      message.error(msg);
      setResults([]);
      setHasMore(false);
    } finally {
      if (requestId === requestIdRef.current) {
        setLoading(false);
      }
    }
  }, [mode, page, query, t]);

  useEffect(() => {
    if (!isSearching) {
      setResults([]);
      setHasMore(false);
      setLoading(false);
      requestIdRef.current += 1;
      setSelectedPaths([]);
      entryCacheRef.current.clear();
      setEntrySnapshot({});
      return;
    }

    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    setSelectedPaths([]);
    closeContextMenus();
    void runSearch(requestId);
  }, [closeContextMenus, isSearching, runSearch]);

  const ensureEntry = useCallback(async (fullPath: string, defaultName: string): Promise<VfsEntry> => {
    const normalized = normalizeFullPath(fullPath);
    const cached = entryCacheRef.current.get(normalized);
    if (cached) {
      return { ...cached, name: cached.name || defaultName };
    }
    try {
      const stat = await vfsApi.stat(normalized);
      const entry: VfsEntry = {
        name: (stat as any)?.name || defaultName,
        is_dir: Boolean((stat as any)?.is_dir),
        size: Number((stat as any)?.size ?? 0),
        mtime: Number((stat as any)?.mtime ?? (stat as any)?.mtime_ms ?? 0),
        type: (stat as any)?.type,
        has_thumbnail: Boolean((stat as any)?.has_thumbnail),
      };
      entryCacheRef.current.set(normalized, entry);
      setEntrySnapshot(prev => ({ ...prev, [normalized]: entry }));
      return entry;
    } catch {
      const fallback: VfsEntry = { name: defaultName, is_dir: false, size: 0, mtime: 0 };
      entryCacheRef.current.set(normalized, fallback);
      setEntrySnapshot(prev => ({ ...prev, [normalized]: fallback }));
      return fallback;
    }
  }, [normalizeFullPath]);

  const refreshSearch = useCallback(() => {
    if (!isSearching) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setLoading(true);
    void runSearch(requestId);
  }, [isSearching, runSearch]);

  useEffect(() => {
    if (!isSearching) {
      setActionPath(currentPath || '/');
      return;
    }
    if (actionPath === '/' && currentPath) {
      setActionPath(currentPath);
    }
  }, [actionPath, currentPath, isSearching]);

  const displayItems = useMemo(() => {
    if (!isSearching) return [];
    return (results || []).map((item) => {
      const { fullPath, dir, name } = splitPath(item.path || '');
      return { item, fullPath, dir, name };
    }).filter(it => it.fullPath && it.fullPath !== '/' && it.name);
  }, [isSearching, results, splitPath]);

  const itemByPath = useMemo(() => {
    const map = new Map<string, SearchDisplayItem>();
    for (const it of displayItems) {
      map.set(it.fullPath, it);
    }
    return map;
  }, [displayItems]);

  useEffect(() => {
    if (!isSearching) return;
    selectedPaths.forEach((p) => {
      const info = itemByPath.get(p);
      if (info) {
        void ensureEntry(info.fullPath, info.name);
      }
    });
  }, [ensureEntry, isSearching, itemByPath, selectedPaths]);

  const updateSearchPage = useCallback((nextPage: number) => {
    const params = new URLSearchParams(location.search);
    if (nextPage <= 1) params.delete('page');
    else params.set('page', String(nextPage));
    const next = params.toString();
    navigate(`${location.pathname}${next ? `?${next}` : ''}`, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const clearSearchParams = useCallback(() => {
    const params = new URLSearchParams(location.search);
    params.delete('q');
    params.delete('mode');
    params.delete('page');
    const next = params.toString();
    navigate(`${location.pathname}${next ? `?${next}` : ''}`, { replace: true });
  }, [location.pathname, location.search, navigate]);

  const openResult = useCallback(async (fullPath: string) => {
    const info = itemByPath.get(fullPath);
    if (!info) return;
    setActionPath(info.dir);
    const entry = await ensureEntry(info.fullPath, info.name);
    if (entry.is_dir) {
      navigateTo(info.fullPath);
      return;
    }
    openFileWithDefaultApp(entry, info.dir);
  }, [ensureEntry, itemByPath, navigateTo, openFileWithDefaultApp]);

  const selectResult = useCallback((fullPath: string, additive: boolean) => {
    const info = itemByPath.get(fullPath);
    if (!info) return;
    if (actionPath !== info.dir) {
      setActionPath(info.dir);
      setSelectedPaths([fullPath]);
      return;
    }
    if (!additive) {
      setSelectedPaths([fullPath]);
      return;
    }
    setSelectedPaths((prev) => {
      const exists = prev.includes(fullPath);
      return exists ? prev.filter(p => p !== fullPath) : [...prev, fullPath];
    });
  }, [actionPath, itemByPath]);

  const openResultContextMenu = useCallback(async (e: React.MouseEvent, fullPath: string) => {
    e.preventDefault();
    e.stopPropagation();
    const info = itemByPath.get(fullPath);
    if (!info) return;
    setActionPath(info.dir);
    setSelectedPaths((prev) => {
      if (actionPath !== info.dir) {
        return [fullPath];
      }
      return prev.includes(fullPath) ? prev : [fullPath];
    });
    const entry = await ensureEntry(info.fullPath, info.name);
    openContextMenu(e, entry);
  }, [actionPath, ensureEntry, itemByPath, openContextMenu]);

  const selectedNames = useMemo(() => {
    const names: string[] = [];
    for (const p of selectedPaths) {
      const info = itemByPath.get(p);
      if (info && info.dir === actionPath) {
        names.push(info.name);
      }
    }
    return names;
  }, [actionPath, itemByPath, selectedPaths]);

  const contextEntries = useMemo(() => {
    if (!isSearching) return [];
    const map = new Map<string, VfsEntry>();
    for (const p of selectedPaths) {
      const info = itemByPath.get(p);
      if (!info || info.dir !== actionPath) continue;
      const cached = entrySnapshot[info.fullPath];
      map.set(info.name, cached || { name: info.name, is_dir: false, size: 0, mtime: 0 });
    }
    if (activeEntry) {
      map.set(activeEntry.name, activeEntry);
    }
    return Array.from(map.values());
  }, [actionPath, activeEntry, entrySnapshot, isSearching, itemByPath, selectedPaths]);

  const totalItems = useMemo(() => {
    if (mode !== 'filename') return results.length;
    if (hasMore) return page * PAGE_SIZE + 1;
    return (page - 1) * PAGE_SIZE + results.length;
  }, [hasMore, mode, page, results.length]);

  const showPagination = isSearching && mode === 'filename' && results.length > 0;

  const clearSelection = useCallback(() => setSelectedPaths([]), []);

  return {
    isSearching,
    query,
    mode,
    page,
    pageSize: PAGE_SIZE,
    loading,
    displayItems,
    selectedPaths,
    selectedNames,
    contextEntries,
    entrySnapshot,
    actionPath,
    showPagination,
    totalItems,
    clearSearchParams,
    updateSearchPage,
    refreshSearch,
    openResult,
    selectResult,
    openResultContextMenu,
    clearSelection,
  };
}

