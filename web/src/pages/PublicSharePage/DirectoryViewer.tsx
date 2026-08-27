import { memo, useState, useEffect, useCallback, useRef } from 'react';
import { Card, List, Typography, Button, Empty, Breadcrumb, Pagination, Space } from 'antd';
import { FileOutlined, FolderOutlined, DownloadOutlined } from '@ant-design/icons';
import { shareApi, type ShareInfo } from '../../api/share';
import { type VfsEntry } from '../../api/vfs';
import { format, parseISO } from 'date-fns';
import { useI18n } from '../../i18n';

const { Title, Text } = Typography;

interface DirectoryViewerProps {
    token: string;
    shareInfo: ShareInfo;
    password?: string;
    onFileClick: (entry: VfsEntry, path: string) => void;
}

const DEFAULT_PAGE_SIZE = 50;

type SharePaginationState = {
    mode: 'paged' | 'cursor';
    current: number;
    pageSize: number;
    total: number;
    cursor: string | null;
    nextCursor: string | null;
    hasNext: boolean;
    cursorHistory: (string | null)[];
};

const INITIAL_PAGINATION: SharePaginationState = {
    mode: 'paged',
    current: 1,
    pageSize: DEFAULT_PAGE_SIZE,
    total: 0,
    cursor: null,
    nextCursor: null,
    hasNext: false,
    cursorHistory: [],
};

export const DirectoryViewer = memo(function DirectoryViewer({ token, shareInfo, password, onFileClick }: DirectoryViewerProps) {
    const [loading, setLoading] = useState(true);
    const [entries, setEntries] = useState<VfsEntry[]>([]);
    const [currentPath, setCurrentPath] = useState('/');
    const [pagination, setPagination] = useState<SharePaginationState>(INITIAL_PAGINATION);
    const [error, setError] = useState('');
    const { t } = useI18n();
    const tRef = useRef(t);
    tRef.current = t;
    const paginationRef = useRef(pagination);
    paginationRef.current = pagination;
    const loadGenRef = useRef(0);
    const abortRef = useRef<AbortController | null>(null);

    const loadData = useCallback(async (opts: {
        path: string;
        page?: number;
        pageSize?: number;
        cursor?: string | null;
        cursorHistory?: (string | null)[];
    }) => {
        const page = opts.page ?? 1;
        const pageSize = opts.pageSize ?? paginationRef.current.pageSize;
        const cursor = opts.cursor ?? null;
        const cursorHistory = opts.cursorHistory ?? [];
        const gen = ++loadGenRef.current;
        abortRef.current?.abort();
        const ac = new AbortController();
        abortRef.current = ac;
        setLoading(true);
        setError('');
        try {
            const listing = await shareApi.listDir(token, opts.path, password, {
                page,
                pageSize,
                cursor,
                signal: ac.signal,
            });
            if (gen !== loadGenRef.current) return;
            const listingPagination = listing.pagination;
            const pageMode = listingPagination?.mode === 'cursor' ? 'cursor' : 'paged';
            setEntries(listing.entries || []);
            setPagination({
                mode: pageMode,
                current: listingPagination?.page ?? page,
                pageSize: listingPagination?.page_size ?? pageSize,
                total: listingPagination?.total ?? 0,
                cursor: listingPagination?.cursor ?? null,
                nextCursor: listingPagination?.next_cursor ?? null,
                hasNext: Boolean(listingPagination?.has_next),
                cursorHistory: pageMode === 'cursor' ? cursorHistory : [],
            });
        } catch (e: any) {
            if (gen !== loadGenRef.current) return;
            if (e?.name === 'AbortError') return;
            setError(e.message || tRef.current('Share load failed'));
        } finally {
            if (gen === loadGenRef.current) {
                setLoading(false);
            }
        }
    }, [password, token]);

    useEffect(() => {
        loadData({ path: currentPath, page: 1 });
        return () => {
            abortRef.current?.abort();
        };
    }, [loadData, currentPath]);

    const goToPath = (path: string) => {
        setPagination(prev => ({
            ...prev,
            current: 1,
            cursor: null,
            nextCursor: null,
            hasNext: false,
            cursorHistory: [],
        }));
        setCurrentPath(path);
    };

    const handleEntryClick = (entry: VfsEntry) => {
        const newPath = (currentPath === '/' ? '' : currentPath) + '/' + entry.name;
        if (entry.is_dir) {
            goToPath(newPath);
        } else {
            onFileClick(entry, newPath);
        }
    };

    const handleBreadcrumbClick = (path: string) => {
        goToPath(path);
    };

    const handlePageChange = (page: number, pageSize: number) => {
        loadData({ path: currentPath, page, pageSize });
    };

    const handleCursorNext = () => {
        if (!pagination.nextCursor) return;
        loadData({
            path: currentPath,
            page: 1,
            pageSize: pagination.pageSize,
            cursor: pagination.nextCursor,
            cursorHistory: [...pagination.cursorHistory, pagination.cursor],
        });
    };

    const handleCursorPrev = () => {
        if (pagination.cursorHistory.length === 0) return;
        const nextHistory = pagination.cursorHistory.slice(0, -1);
        const prevCursor = pagination.cursorHistory[pagination.cursorHistory.length - 1];
        loadData({
            path: currentPath,
            page: 1,
            pageSize: pagination.pageSize,
            cursor: prevCursor,
            cursorHistory: nextHistory,
        });
    };

    const renderBreadcrumb = () => {
        const parts = currentPath.split('/').filter(Boolean);
        const items = [{ title: t('Root'), path: '/' }];
        parts.forEach((part, i) => {
            const path = '/' + parts.slice(0, i + 1).join('/');
            items.push({ title: part, path });
        });
        return (
            <Breadcrumb>
                {items.map((item, i) => (
                    <Breadcrumb.Item key={i}>
                        {i === items.length - 1 ? (
                            <span>{item.title}</span>
                        ) : (
                            <a onClick={() => handleBreadcrumbClick(item.path)}>{item.title}</a>
                        )}
                    </Breadcrumb.Item>
                ))}
            </Breadcrumb>
        );
    };

    const showPagedPagination = pagination.mode === 'paged' && pagination.total > 0;
    const showCursorPagination = pagination.mode === 'cursor' && (pagination.cursorHistory.length > 0 || pagination.hasNext);

    if (error) {
        return <div style={{ textAlign: 'center', padding: 50 }}><Empty description={error} /></div>;
    }

    return (
        <div style={{ padding: '24px', maxWidth: 960, margin: 'auto' }}>
            <Card>
                <Title level={4}>{shareInfo?.name}</Title>
                <Text type="secondary">
                    {t('Created on {date}', { date: format(parseISO(shareInfo.created_at), 'yyyy-MM-dd') })}
                    {shareInfo?.expires_at ? (
                      <>
                        {' '}
                        {t('Expires on {date}', { date: format(parseISO(shareInfo.expires_at), 'yyyy-MM-dd') })}
                      </>
                    ) : null}
                </Text>
                <div style={{ margin: '16px 0' }}>
                    {renderBreadcrumb()}
                </div>
                <List
                    loading={loading}
                    dataSource={entries}
                    renderItem={item => (
                        <List.Item
                            actions={[
                                !item.is_dir ? <Button type="text" icon={<DownloadOutlined />} href={shareApi.downloadUrl(token!, (currentPath === '/' ? '' : currentPath) + '/' + item.name, password)} download /> : null
                            ]}
                        >
                            <List.Item.Meta
                                avatar={item.is_dir ? <FolderOutlined /> : <FileOutlined />}
                                title={<a onClick={() => handleEntryClick(item)}>{item.name}</a>}
                                description={!item.is_dir ? `${(item.size / 1024).toFixed(2)} KB` : ''}
                            />
                        </List.Item>
                    )}
                />
                {showPagedPagination ? (
                    <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                        <Pagination
                            current={pagination.current}
                            pageSize={pagination.pageSize}
                            total={pagination.total}
                            showSizeChanger
                            pageSizeOptions={['20', '50', '100', '200']}
                            showTotal={(total, range) => `${total} ${t('items')} ${range[0]}-${range[1]}`}
                            onChange={handlePageChange}
                        />
                    </div>
                ) : null}
                {showCursorPagination ? (
                    <div style={{ display: 'flex', justifyContent: 'center', marginTop: 16 }}>
                        <Space>
                            <Button size="small" onClick={handleCursorPrev} disabled={pagination.cursorHistory.length === 0 || loading}>
                                {t('Previous page')}
                            </Button>
                            <Button size="small" type="primary" onClick={handleCursorNext} disabled={!pagination.hasNext || loading}>
                                {t('Next page')}
                            </Button>
                        </Space>
                    </div>
                ) : null}
            </Card>
        </div>
    );
});
