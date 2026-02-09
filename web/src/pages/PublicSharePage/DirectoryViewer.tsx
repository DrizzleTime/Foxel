import { memo, useState, useEffect, useCallback } from 'react';
import { Card, List, Typography, Button, Empty, Breadcrumb } from 'antd';
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

export const DirectoryViewer = memo(function DirectoryViewer({ token, shareInfo, password, onFileClick }: DirectoryViewerProps) {
    const [loading, setLoading] = useState(true);
    const [entries, setEntries] = useState<VfsEntry[]>([]);
    const [currentPath, setCurrentPath] = useState('/');
    const [error, setError] = useState('');
    const { t } = useI18n();

	    const loadData = useCallback(async (p: string) => {
	        setLoading(true);
	        setError('');
	        try {
	            const listing = await shareApi.listDir(token, p, password);
	            setEntries(listing.entries || []);
	            setCurrentPath(p);
	        } catch (e: any) {
	            setError(e.message || t('Share load failed'));
	        } finally {
	            setLoading(false);
	        }
	    }, [password, t, token]);

    useEffect(() => {
        loadData(currentPath);
    }, [loadData, currentPath]);

    const handleEntryClick = (entry: VfsEntry) => {
        const newPath = (currentPath === '/' ? '' : currentPath) + '/' + entry.name;
        if (entry.is_dir) {
            loadData(newPath);
        } else {
            onFileClick(entry, newPath);
        }
    };

    const handleBreadcrumbClick = (path: string) => {
        loadData(path);
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
            </Card>
        </div>
    );
});
