import { useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { message } from 'antd';
import { vfsApi, type VfsEntry } from '../../../api/client';

type ExplorerSnapshot = {
  path: string;
  entries: VfsEntry[];
  pagination?: {
    total: number;
    page: number;
    page_size: number;
    pages: number;
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
    showSizeChanger: true,
    showQuickJumper: true,
    showTotal: (total: number, range: [number, number]) => `${total} ${'items'} ${range[0]}-${range[1]}`,
    pageSizeOptions: ['20', '50', '100', '200']
  });
  const [sortBy, setSortBy] = useState('name');
  const [sortOrder, setSortOrder] = useState('asc');

  const load = useCallback(async (p: string, page: number = 1, pageSize: number = 50, sb = sortBy, so = sortOrder) => {
    const canonical = p === '' ? '/' : (p.startsWith('/') ? p : '/' + p);
    setLoading(true);
    try {
      // Load entries and processor types concurrently
      const [res, processors] = await Promise.all([
        vfsApi.list(canonical === '/' ? '' : canonical, page, pageSize, sb, so),
        processorsApi.list()
      ]);
      setEntries(res.entries);
      const resolvedPath = res.path || canonical;
      setPath(resolvedPath);
      setPagination(prev => ({
        ...prev,
        current: res.pagination!.page,
        pageSize: res.pagination!.page_size,
        total: res.pagination!.total
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

  const refresh = () => {
    load(path, pagination.current, pagination.pageSize, sortBy, sortOrder);
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
    handleSortChange
  };
}
