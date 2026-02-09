import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Form, Input, InputNumber, message, Progress, Row, Segmented, Select, Space, Table, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import PageCard from '../components/PageCard';
import { tasksApi, type QueuedTask, type TaskQueueSettings } from '../api/tasks';
import { useI18n } from '../i18n';
import { SearchOutlined } from '@ant-design/icons';

type QueueStatus = QueuedTask['status'];

const AUTO_REFRESH_INTERVAL = 5000;

const TaskQueuePage = memo(function TaskQueuePage() {
  const { t } = useI18n();
  const [messageApi, contextHolder] = message.useMessage();
  const [tasks, setTasks] = useState<QueuedTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [statusFilter, setStatusFilter] = useState<QueueStatus[]>(['pending', 'running']);
  const [autoRefresh, setAutoRefresh] = useState<'on' | 'off'>('on');
  const [settings, setSettings] = useState<TaskQueueSettings>({ concurrency: 1, active_workers: 0 });
  const [concurrencyDraft, setConcurrencyDraft] = useState<number>(1);
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const statusOptions = useMemo(() => ([
    { label: t('Pending'), value: 'pending' },
    { label: t('Running'), value: 'running' },
    { label: t('Success'), value: 'success' },
    { label: t('Failed'), value: 'failed' },
  ]), [t]);

  const loadTasks = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const data = await tasksApi.getQueue();
      setTasks(data);
      setLastUpdated(Date.now());
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : t('Load failed');
      messageApi.error(msg);
    } finally {
      if (withSpinner) setLoading(false);
    }
  }, [messageApi, t]);

  const loadSettings = useCallback(async () => {
    try {
      const data = await tasksApi.getQueueSettings();
      setSettings(data);
      setConcurrencyDraft(data.concurrency);
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : t('Load failed');
      messageApi.error(msg);
    }
  }, [messageApi, t]);

  useEffect(() => {
    loadTasks(true).catch(() => {});
    loadSettings().catch(() => {});
  }, [loadTasks, loadSettings]);

  useEffect(() => {
    if (autoRefresh === 'off') return () => {};
    const timer = window.setInterval(() => {
      loadTasks().catch(() => {});
    }, AUTO_REFRESH_INTERVAL);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadTasks]);

  const metrics = useMemo(() => {
    const counts = {
      total: tasks.length,
      pending: 0,
      running: 0,
      success: 0,
      failed: 0,
    };
    tasks.forEach(task => {
      counts[task.status] += 1;
    });
    return counts;
  }, [tasks]);

  const filteredTasks = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    return tasks.filter(task => {
      if (statusFilter.length > 0 && !statusFilter.includes(task.status)) return false;
      if (!normalizedKeyword) return true;
      const haystack = [
        task.id,
        task.name,
        JSON.stringify(task.task_info ?? {}),
        task.meta ? JSON.stringify(task.meta) : '',
        task.error ?? '',
      ].join(' ').toLowerCase();
      return haystack.includes(normalizedKeyword);
    });
  }, [keyword, statusFilter, tasks]);

  const progressLabel = useCallback((task: QueuedTask) => {
    const percent = task.progress?.percent;
    const stage = task.progress?.stage;
    if (percent !== undefined && percent !== null) {
      const percentText = `${percent.toFixed(1)}%`;
      return stage ? `${percentText} · ${stage}` : percentText;
    }
    return stage ?? '--';
  }, []);

  const columns: ColumnsType<QueuedTask> = useMemo(() => ([
    {
      title: 'ID',
      dataIndex: 'id',
      width: 160,
      render: (id: string) => (
        <Tooltip title={id}>
          <Tag color="default" style={{ cursor: 'pointer', margin: 0 }}>
            <Typography.Text style={{ fontSize: 12 }} copyable={{ text: id }}>
              {id.slice(0, 8)}
            </Typography.Text>
          </Tag>
        </Tooltip>
      ),
    },
    {
      title: t('Task Type'),
      dataIndex: 'name',
      sorter: (a, b) => a.name.localeCompare(b.name),
      width: 160,
    },
    {
      title: t('Status'),
      dataIndex: 'status',
      width: 120,
      render: (status: QueueStatus) => {
        const colorMap: Record<QueueStatus, string> = {
          pending: 'default',
          running: 'processing',
          success: 'success',
          failed: 'error',
        };
        const labelMap: Record<QueueStatus, string> = {
          pending: t('Pending'),
          running: t('Running'),
          success: t('Success'),
          failed: t('Failed'),
        };
        return <Tag color={colorMap[status]}>{labelMap[status]}</Tag>;
      },
    },
    {
      title: t('Progress'),
      render: (_: unknown, record) => (
        record.progress?.percent !== undefined && record.progress.percent !== null
          ? <Progress percent={Number(record.progress.percent.toFixed(1))} size="small" status={record.status === 'failed' ? 'exception' : record.status === 'success' ? 'success' : 'active'} />
          : <Typography.Text type="secondary" style={{ fontSize: 12 }}>{progressLabel(record)}</Typography.Text>
      ),
    },
    {
      title: t('Details'),
      dataIndex: 'task_info',
      render: (_: unknown, record) => {
        const info = record.task_info ? JSON.stringify(record.task_info) : '--';
        return (
          <Typography.Paragraph
            ellipsis={{ rows: 2, expandable: true, symbol: t('Expand') }}
            style={{ marginBottom: 0, fontFamily: 'Menlo, Consolas, monospace', fontSize: 12 }}
          >
            {info}
          </Typography.Paragraph>
        );
      },
    },
    {
      title: t('Error'),
      dataIndex: 'error',
      render: (error: string | undefined) => error ? <Typography.Text type="danger">{error}</Typography.Text> : '--',
    },
  ]), [progressLabel, t]);

  const handleSaveSettings = useCallback(async () => {
    setSettingsLoading(true);
    try {
      const next = await tasksApi.updateQueueSettings({ concurrency: concurrencyDraft });
      setSettings(next);
      setConcurrencyDraft(next.concurrency);
      messageApi.success(t('Settings saved'));
      await loadTasks();
    } catch (err) {
      const msg = err instanceof Error && err.message ? err.message : t('Operation failed');
      messageApi.error(msg);
    } finally {
      setSettingsLoading(false);
    }
  }, [concurrencyDraft, loadTasks, messageApi, t]);

  const lastUpdatedText = useMemo(() => {
    if (!lastUpdated) return '--';
    return new Date(lastUpdated).toLocaleTimeString();
  }, [lastUpdated]);

  return (
    <>
      {contextHolder}
      <PageCard
        title={t('Task Queue')}
        extra={
          <Space size={16} wrap>
            <Typography.Text type="secondary">{t('Last updated at {time}', { time: lastUpdatedText })}</Typography.Text>
            <Segmented
              options={[{ label: t('Auto'), value: 'on' }, { label: t('Manual'), value: 'off' }]}
              value={autoRefresh}
              onChange={(value) => setAutoRefresh(value as 'on' | 'off')}
            />
            <Button onClick={() => loadTasks(true)} loading={loading} type="default" disabled={autoRefresh === 'on'}>
              {t('Refresh')}
            </Button>
          </Space>
        }
      >
        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          {[{
            label: t('Total Tasks'), value: metrics.total, color: '#1677ff'
          }, {
            label: t('Running Tasks'), value: metrics.running, color: '#52c41a'
          }, {
            label: t('Waiting Tasks'), value: metrics.pending, color: '#faad14'
          }, {
            label: t('Failed Tasks'), value: metrics.failed, color: '#ff4d4f'
          }, {
            label: t('Active Workers'), value: settings.active_workers, color: '#722ed1'
          }].map((item) => (
            <Col key={item.label} xs={24} sm={12} md={8} lg={6} xl={4}>
              <Card size="small" bodyStyle={{ padding: '12px 16px' }}>
                <Typography.Text type="secondary">{item.label}</Typography.Text>
                <Typography.Title level={4} style={{ margin: '4px 0 0', color: item.color }}>{item.value}</Typography.Title>
              </Card>
            </Col>
          ))}
        </Row>

        <Form layout="inline" style={{ marginBottom: 16, gap: 16, flexWrap: 'wrap' }}>
          <Form.Item>
            <Input
              allowClear
              placeholder={t('Search by name or ID')}
              prefix={<SearchOutlined style={{ color: 'var(--ant-color-text-tertiary)' }} />}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ width: 260 }}
            />
          </Form.Item>
          <Form.Item>
            <Select
              mode="multiple"
              allowClear
              placeholder={t('Filter by status')}
              value={statusFilter}
              maxTagCount={2}
              onChange={(value) => setStatusFilter(value as QueueStatus[])}
              options={statusOptions}
              style={{ minWidth: 220 }}
            />
          </Form.Item>
          <Form.Item>
            <Tooltip title={t('Adjust worker concurrency immediately')}>
              <Space size={8}>
                <Typography.Text>{t('Queue Concurrency')}:</Typography.Text>
                <InputNumber
                  min={1}
                  controls={false}
                  style={{ width: 80 }}
                  value={concurrencyDraft}
                  onChange={(value) => setConcurrencyDraft(value ?? 1)}
                />
                <Button type="primary" onClick={handleSaveSettings} loading={settingsLoading}>
                  {t('Save')}
                </Button>
              </Space>
            </Tooltip>
          </Form.Item>
        </Form>

        <Table
          rowKey="id"
          dataSource={filteredTasks}
          columns={columns}
          loading={loading}
          pagination={{ pageSize: 10 }}
          style={{ marginBottom: 0 }}
        />
      </PageCard>
    </>
  );
});

export default TaskQueuePage;
