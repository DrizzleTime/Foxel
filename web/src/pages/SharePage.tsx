import { memo, useState, useEffect, useCallback } from 'react';
import { Table, Button, Space, message, Popconfirm, Tag, Tooltip } from 'antd';
import PageCard from '../components/PageCard';
import { shareApi, type ShareInfo } from '../api/share';
import { format, parseISO } from 'date-fns';
import { LinkOutlined, CopyOutlined, DeleteOutlined } from '@ant-design/icons';
import { useSystemStatus } from '../contexts/SystemContext';
import { useI18n } from '../i18n';

const SharePage = memo(function SharePage() {
  const systemStatus = useSystemStatus();
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<ShareInfo[]>([]);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const list = await shareApi.list();
      setData(list);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { fetchList(); }, [fetchList]);

  const doCopy = (rec: ShareInfo) => {
    const baseUrl = systemStatus?.app_domain || window.location.origin;
    const shareUrl = new URL(`/share/${rec.token}`, baseUrl).href;
    navigator.clipboard.writeText(shareUrl);
    message.success(t('Copied link'));
  };

  const doDelete = async (rec: ShareInfo) => {
    try {
      await shareApi.remove(rec.id);
      message.success(t('Share canceled'));
      fetchList();
    } catch (e: any) {
      message.error(e.message || t('Cancel failed'));
    }
  };

  const handleClearExpired = async () => {
    try {
      const res = await shareApi.clearExpired();
      message.success(t('Cleared {count} expired shares', { count: String(res.deleted_count) }));
      fetchList();
    } catch (e: any) {
      message.error(e.message || t('Clear failed'));
    }
  };

  const columns = [
    { 
      title: t('Share Name'), 
      dataIndex: 'name',
      render: (name: string, rec: ShareInfo) => (
        <a href={`/share/${rec.token}`} target="_blank" rel="noopener noreferrer">
          <LinkOutlined style={{ marginRight: 8 }} />
          {name}
        </a>
      )
    },
    { 
      title: t('Share Content'), 
      dataIndex: 'paths',
      ellipsis: true,
      render: (paths: string[]) => (
        <Tooltip title={paths.join(', ')}>
          <span>{paths.join(', ')}</span>
        </Tooltip>
      )
    },
    { 
      title: t('Created At'), 
      dataIndex: 'created_at', 
      width: 180,
      render: (v: string) => format(parseISO(v), 'yyyy-MM-dd HH:mm')
    },
    {
      title: t('Expires At'),
      dataIndex: 'expires_at',
      width: 180,
      render: (v?: string) => v ? <Tag color="orange">{format(parseISO(v), 'yyyy-MM-dd HH:mm')}</Tag> : <Tag>{t('Forever')}</Tag>
    },
    {
      title: t('Access'),
      dataIndex: 'access_type',
      width: 100,
      render: (v: 'public' | 'password') => v === 'password' ? <Tag color="red">{t('By Password')}</Tag> : <Tag color="green">{t('Public')}</Tag>
    },
    {
      title: '',
      width: 160,
      render: (_: any, rec: ShareInfo) => (
        <Space size="small">
          <Button size="small" icon={<CopyOutlined />} onClick={() => doCopy(rec)}>{t('Copy')}</Button>
          <Popconfirm title={t('Are you sure to cancel share?')} onConfirm={() => doDelete(rec)}>
            <Button size="small" danger icon={<DeleteOutlined />}>{t('Cancel')}</Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  return (
    <PageCard
      title={t('My Shares')}
      extra={
        <Space>
          <Button onClick={fetchList} loading={loading}>{t('Refresh')}</Button>
          <Popconfirm title={t('Confirm clear expired shares?')} onConfirm={handleClearExpired}>
            <Button danger>{t('Clear expired shares')}</Button>
          </Popconfirm>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={data}
        columns={columns as any}
        loading={loading}
        pagination={false}
      />
    </PageCard>
  );
});

export default SharePage;
