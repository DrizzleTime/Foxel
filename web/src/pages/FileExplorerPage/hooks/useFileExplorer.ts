import { useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { message } from 'antd';
import { vfsApi, type VfsEntry } from '../../../api/client';

type ExplorerSnapshot = {
  path: string;
  entries: VfsEntry[];
  pagination?: {
    mode?: 'paged' | 'cursor';
    page_size: number;
    total?: number;
    page?: number;
    pages?: number;
    cursor?: string | null;
    next_cursor?: string | null;
    has_next?: boolean;
  };
  sortBy: string;
  sortOrder: string;
  timestamp: number;
};
import { processorsApi, type ProcessorTypeMeta } from '../../../api/processors';

export function useFileExplorer(navKey: string) {
  const navigate = useNavigate();
  const location = useLocation();

  const [path, setPath] = useState<string>("/");
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<VfsEntry[]>([]);
  const [processorTypes, setProcessorTypes] = useState<ProcessorTypeMeta[]>([]);
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 50,
    total: 0,
    mode: 'paged' as 'paged' | 'cursor',
    cursor: null as string | null,
    nextCursor: null as string | null,
    cursorHistory: [] as (string | null)[],
    hasNext: false,
    showSizeChanger: true,
    showQuickJumper: true,
    showTotal: (total: number, range: [number, number]) => `${total} ${'items'} ${range[0]}-${range[1]}`,
    pageSizeOptions: ['20', '50', '100', '200']
  });
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const load = useCallback(async (p: string, page: number = 1, pageSize: number = 50, sb = sortBy, so = sortOrder, cursor?: string | null, cursorHistory: (string | null)[] = []) => {
    const canonical = p === '' ? '/' : (p.startsWith('/') ? p : '/' + p);
    setLoading(true);
    try {
      // Load entries and processor types concurrently
      const [res, processors] = await Promise.all([
        vfsApi.list(canonical === '/' ? '' : canonical, page, pageSize, sb, so, cursor),
        processorsApi.list()
      ]);
      setEntries(res.entries);
      const resolvedPath = res.path || canonical;
      setPath(resolvedPath);
      const pageMode = res.pagination?.mode || 'paged';
      setPagination(prev => ({
        ...prev,
        mode: pageMode,
        current: res.pagination?.page || page,
        pageSize: res.pagination?.page_size || pageSize,
        total: res.pagination?.total || 0,
        cursor: res.pagination?.cursor || null,
        nextCursor: res.pagination?.next_cursor || null,
        hasNext: Boolean(res.pagination?.has_next),
        cursorHistory: pageMode === 'cursor' ? cursorHistory : [],
      }));
      setProcessorTypes(processors);
      if (typeof window !== 'undefined') {
        const snapshot: ExplorerSnapshot = {
          path: resolvedPath,
          entries: res.entries,
          pagination: res.pagination,
          sortBy: sb,
          sortOrder: so,
          timestamp: Date.now(),
        };
        const explorerWindow = window as Window & { __FOXEL_LAST_EXPLORER_PAGE__?: ExplorerSnapshot };
        explorerWindow.__FOXEL_LAST_EXPLORER_PAGE__ = snapshot;
        window.dispatchEvent(new CustomEvent<ExplorerSnapshot>('foxel:file-explorer-page', { detail: snapshot }));
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Load failed';
      message.error(msg);
    } finally {
      setLoading(false);
    }
  }, [sortBy, sortOrder]);

  const navigateTo = useCallback((p: string) => {
    const canonical = p === '' || p === '/' ? '/' : (p.startsWith('/') ? p : '/' + p);
    const target = `/${navKey}${canonical === '/' ? '' : canonical}`;
    if (location.pathname !== target) navigate(target);
  }, [navKey, navigate, location.pathname]);

  const goUp = useCallback(() => {
    if (path === '/') return;
    const parent = path.replace(/\/$/, '').split('/').slice(0, -1).join('/') || '/';
    navigateTo(parent);
  }, [path, navigateTo]);

  const handlePaginationChange = (page: number, pageSize: number) => {
    load(path, page, pageSize, sortBy, sortOrder);
  };

  const goCursorNext = () => {
    if (!pagination.nextCursor) return;
    load(path, 1, pagination.pageSize, sortBy, sortOrder, pagination.nextCursor, [
      ...pagination.cursorHistory,
      pagination.cursor,
    ]);
  };

  const goCursorPrev = () => {
    if (pagination.cursorHistory.length === 0) return;
    const nextHistory = pagination.cursorHistory.slice(0, -1);
    const prevCursor = pagination.cursorHistory[pagination.cursorHistory.length - 1];
    load(path, 1, pagination.pageSize, sortBy, sortOrder, prevCursor, nextHistory);
  };

  const refresh = () => {
    load(
      path,
      pagination.current,
      pagination.pageSize,
      sortBy,
      sortOrder,
      pagination.mode === 'cursor' ? pagination.cursor : null,
      pagination.mode === 'cursor' ? pagination.cursorHistory : [],
    );
  }

  const handleSortChange = (sb: string, so: string) => {
    setSortBy(sb);
    setSortOrder(so);
    load(path, 1, pagination.pageSize, sb, so);
  };

  return {
    path,
    entries,
    loading,
    pagination,
    processorTypes,
    sortBy,
    sortOrder,
    load,
    navigateTo,
    goUp,
    handlePaginationChange,
    refresh,
    handleSortChange,
    goCursorNext,
    goCursorPrev,
  };
}
