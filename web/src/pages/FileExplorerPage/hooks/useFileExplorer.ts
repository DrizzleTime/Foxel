import { useState, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router';
import { message } from 'antd';
import { vfsApi, type VfsEntry } from '../../../api/client';
import { processorsApi, type ProcessorTypeMeta } from '../../../api/processors';

export function useFileExplorer(navKey: string) {
  const navigate = useNavigate();
  const location = useLocation();

  const [path, setPath] = useState<string>("/");
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<VfsEntry[]>([]);
  const [processorTypes, setProcessorTypes] = useState<ProcessorTypeMeta[]>([]);
  const [sortBy, setSortBy] = useState<string>("name");
  const [sortOrder, setSortOrder] = useState<string>("asc");
  const [pagination, setPagination] = useState({
    current: 1,
    pageSize: 50,
    total: 0,
    showSizeChanger: true,
    showQuickJumper: true,
    showTotal: (total: number, range: [number, number]) => `共 ${total} 项，第 ${range[0]}-${range[1]} 项`,
    pageSizeOptions: ['20', '50', '100', '200']
  });

  const load = useCallback(async (p: string, page: number = 1, pageSize: number = 50) => {
    const canonical = p === '' ? '/' : (p.startsWith('/') ? p : '/' + p);
    setLoading(true);
    try {
      // Load entries and processor types concurrently
      const [res, processors] = await Promise.all([
        vfsApi.list(canonical === '/' ? '' : canonical, page, pageSize, sortBy, sortOrder),
        processorsApi.list()
      ]);
      setEntries(res.entries);
      setPath(res.path || canonical);
      setPagination(prev => ({
        ...prev,
        current: res.pagination!.page,
        pageSize: res.pagination!.page_size,
        total: res.pagination!.total
      }));
      setProcessorTypes(processors);
    } catch (e: any) {
      message.error(e.message || '加载失败');
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
    load(path, page, pageSize);
  };

  const refresh = () => {
    load(path, pagination.current, pagination.pageSize);
  }

  const handleSortChange = (newSortBy: string, newSortOrder: string) => {
    setSortBy(newSortBy);
    setSortOrder(newSortOrder);
    load(path, 1, pagination.pageSize); // Reset to first page when sorting changes
  }

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
  };
}