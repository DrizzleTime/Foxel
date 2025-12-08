import { memo, useState, useEffect, useCallback } from 'react';
import { Table, message, Tag, Input, Select, Button, Space, Modal, DatePicker, Descriptions, Divider, Typography } from 'antd';
import PageCard from '../components/PageCard';
import { auditApi, type AuditLogItem, type PaginatedAuditLogs } from '../api/audit';
import { useI18n } from '../i18n';
import { format, formatISO } from 'date-fns';

const { RangePicker } = DatePicker;

const ACTION_OPTIONS = [
  'login',
  'logout',
  'register',
  'read',
  'create',
  'update',
  'delete',
  'reset_password',
  'share',
  'download',
  'upload',
  'other'
];

const AuditLogsPage = memo(function AuditLogsPage() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PaginatedAuditLogs | null>(null);
  const [filters, setFilters] = useState<{
    page: number;
    page_size: number;
    action: string;
    success: '' | boolean;
    username: string;
    path: string;
    start_time: string;
    end_time: string;
  }>({
    page: 1,
    page_size: 20,
    action: '',
    success: '',
    username: '',
    path: '',
    start_time: '',
    end_time: '',
  });
  const [selectedLog, setSelectedLog] = useState<AuditLogItem | null>(null);
  const { t } = useI18n();

  const buildParams = () => {
    const params: any = { ...filters };
    if (!params.action) delete params.action;
    if (params.success === '') delete params.success;
    if (!params.username) delete params.username;
    if (!params.path) delete params.path;
    if (!params.start_time) delete params.start_time;
    if (!params.end_time) delete params.end_time;
    return params;
  };

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await auditApi.list(buildParams());
      setData(res);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchList();
  }, [fetchList]);

  const handleClearLogs = () => {
    if (!filters.start_time && !filters.end_time) {
      message.warning(t('Please select time range'));
      return;
    }
    Modal.confirm({
      title: t('Confirm clear logs?'),
      content: t('This will delete logs in selected range irreversibly.'),
      onOk: async () => {
        try {
          const params: any = {};
          if (filters.start_time) params.start_time = filters.start_time;
          if (filters.end_time) params.end_time = filters.end_time;
          const res = await auditApi.clear(params);
          message.success(t('Cleared {count} logs', { count: String(res.deleted_count) }));
          fetchList();
        } catch (e: any) {
          message.error(e.message || t('Clear failed'));
        }
      },
    });
  };

  const columns = [
    {
      title: t('Time'),
      dataIndex: 'created_at',
      width: 180,
      render: (ts: string) => format(new Date(ts), 'yyyy-MM-dd HH:mm:ss'),
    },
    {
      title: t('Action'),
      dataIndex: 'action',
      width: 140,
      render: (action: string) => <Tag color="blue">{action}</Tag>,
    },
    {
      title: t('User'),
      dataIndex: 'username',
      width: 160,
      render: (_: any, rec: AuditLogItem) => rec.username || rec.user_id || '-',
    },
    {
      title: t('Path'),
      dataIndex: 'path',
      ellipsis: true,
      render: (path: string, rec: AuditLogItem) => (
        <Space size={4}>
          <Tag bordered={false} color="default" style={{ margin: 0, paddingInline: 8 }}>{rec.method}</Tag>
          <span style={{ maxWidth: 320, display: 'inline-block' }}>{path}</span>
        </Space>
      ),
    },
    {
      title: t('Status Code'),
      dataIndex: 'status_code',
      width: 100,
    },
    {
      title: t('Duration (ms)'),
      dataIndex: 'duration_ms',
      width: 120,
      render: (ms?: number | null) => (ms !== null && ms !== undefined ? ms : '-'),
    },
    {
      title: t('Client IP'),
      dataIndex: 'client_ip',
      width: 140,
      render: (ip?: string | null) => ip || '-',
    },
    {
      title: t('Result'),
      dataIndex: 'success',
      width: 100,
      render: (success: boolean) => (
        <Tag color={success ? 'green' : 'red'}>
          {success ? t('Success') : t('Failure')}
        </Tag>
      ),
    },
    {
      title: t('Actions'),
      width: 100,
      render: (_: any, rec: AuditLogItem) => (
        <Button size="small" onClick={() => setSelectedLog(rec)}>{t('Details')}</Button>
      ),
    },
  ];

  return (
    <PageCard
      title={t('Audit Logs')}
      extra={
        <Space align="center" wrap size={[8, 8]}>
          <RangePicker
            showTime
            size="small"
            onChange={dates => {
              setFilters(f => ({
                ...f,
                start_time: dates?.[0] ? formatISO(dates[0].toDate()) : '',
                end_time: dates?.[1] ? formatISO(dates[1].toDate()) : '',
                page: 1,
              }));
            }}
          />
          <Select
            style={{ width: 120 }}
            placeholder={t('Action')}
            allowClear
            size="small"
            value={filters.action || undefined}
            onChange={action => setFilters(f => ({ ...f, action: action || '', page: 1 }))}
            options={ACTION_OPTIONS.map(a => ({ value: a, label: a }))}
          />
          <Select
            style={{ width: 120 }}
            placeholder={t('Result')}
            allowClear
            size="small"
            value={filters.success === '' ? undefined : filters.success}
            onChange={value => setFilters(f => ({ ...f, success: (value as boolean) ?? '', page: 1 }))}
            options={[
              { value: true, label: t('Success') },
              { value: false, label: t('Failure') },
            ]}
          />
          <Input.Search
            style={{ width: 120 }}
            placeholder={t('Username')}
            size="small"
            allowClear
            value={filters.username}
            onChange={e => setFilters(f => ({ ...f, username: e.target.value }))}
            onSearch={username => setFilters(f => ({ ...f, username, page: 1 }))}
          />
          <Button onClick={fetchList} loading={loading}>{t('Refresh')}</Button>
          <Button danger onClick={handleClearLogs}>{t('Clear')}</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={data?.items}
        columns={columns}
        loading={loading}
        pagination={{
          current: filters.page,
          pageSize: filters.page_size,
          total: data?.total,
          showSizeChanger: true,
          onChange: (page, pageSize) => setFilters(f => ({ ...f, page, page_size: pageSize })),
        }}
        scroll={{ x: 900 }}
      />
      <Modal
        title={t('Audit Log Details')}
        open={!!selectedLog}
        onCancel={() => setSelectedLog(null)}
        footer={null}
        width={900}
        styles={{ body: { maxHeight: '70vh', overflowY: 'auto' } }}
      >
        {selectedLog && (
          <Space direction="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions
              column={2}
              bordered
              size="small"
              labelStyle={{ minWidth: 120, whiteSpace: 'nowrap', fontWeight: 500 }}
              contentStyle={{ wordBreak: 'break-all', whiteSpace: 'pre-wrap' }}
            >
              <Descriptions.Item label={t('Time')}>
                {format(new Date(selectedLog.created_at), 'yyyy-MM-dd HH:mm:ss')}
              </Descriptions.Item>
              <Descriptions.Item label={t('Action')}>
                <Tag color="blue">{selectedLog.action}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('User')}>
                {selectedLog.username || selectedLog.user_id || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('Client IP')}>
                {selectedLog.client_ip || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('Path')} span={2}>
                <Space size={6} wrap style={{ wordBreak: 'break-all' }}>
                  <Tag bordered={false} color="default" style={{ margin: 0, paddingInline: 8 }}>{selectedLog.method}</Tag>
                  <Typography.Text copyable style={{ wordBreak: 'break-all' }}>{selectedLog.path}</Typography.Text>
                </Space>
              </Descriptions.Item>
              <Descriptions.Item label={t('Status Code')}>
                {selectedLog.status_code}
              </Descriptions.Item>
              <Descriptions.Item label={t('Duration (ms)')}>
                {selectedLog.duration_ms ?? '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('Result')}>
                <Tag color={selectedLog.success ? 'green' : 'red'}>
                  {selectedLog.success ? t('Success') : t('Failure')}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label={t('Description')} span={2}>
                {selectedLog.description || '-'}
              </Descriptions.Item>
              <Descriptions.Item label={t('Error')} span={2}>
                {selectedLog.error || '-'}
              </Descriptions.Item>
            </Descriptions>
            <Divider style={{ margin: '12px 0 0' }} />
            <Typography.Title level={5} style={{ margin: 0 }}>
              {t('Request Params')}
            </Typography.Title>
            <pre style={{ maxHeight: 200, overflow: 'auto', background: 'var(--ant-color-fill-tertiary, #f5f5f5)', padding: 12 }}>
              {selectedLog.request_params ? JSON.stringify(selectedLog.request_params, null, 2) : '-'}
            </pre>
            <Typography.Title level={5} style={{ margin: 0 }}>
              {t('Request Body')}
            </Typography.Title>
            <pre style={{ maxHeight: 200, overflow: 'auto', background: 'var(--ant-color-fill-tertiary, #f5f5f5)', padding: 12 }}>
              {selectedLog.request_body ? JSON.stringify(selectedLog.request_body, null, 2) : '-'}
            </pre>
          </Space>
        )}
      </Modal>
    </PageCard>
  );
});

export default AuditLogsPage;
