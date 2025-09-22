import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Modal, message, Table, Tag, Typography, Space } from 'antd';
import type { TableColumnsType } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';

import PathSelectorModal from '../components/PathSelectorModal';
import { offlineDownloadsApi, type OfflineDownloadTask } from '../api/client';
import { useI18n } from '../i18n';
import PageCard from '../components/PageCard';

interface TableRow extends OfflineDownloadTask {
  key: string;
}

function formatBytes(bytes?: number | null): string {
  if (bytes === undefined || bytes === null) return '--';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const idx = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const val = bytes / Math.pow(1024, idx);
  return `${val.toFixed(idx === 0 ? 0 : 1)} ${units[idx]}`;
}

function stageLabel(t: (key: string) => string, stage?: string | null): string {
  if (!stage) return '--';
  const map: Record<string, string> = {
    queued: t('Queued'),
    downloading: t('Downloading'),
    transferring: t('Transferring'),
    completed: t('Completed'),
  };
  return map[stage] ?? stage;
}

function statusTag(status: OfflineDownloadTask['status'], t: (key: string) => string) {
  switch (status) {
    case 'success':
      return <Tag color="green">{t('Success')}</Tag>;
    case 'failed':
      return <Tag color="red">{t('Failed')}</Tag>;
    case 'running':
      return <Tag color="blue">{t('Running')}</Tag>;
    default:
      return <Tag color="default">{t('Pending')}</Tag>;
  }
}

const OfflineDownloadPage = memo(function OfflineDownloadPage() {
  const { t } = useI18n();
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  const [tasks, setTasks] = useState<TableRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [pathModalOpen, setPathModalOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  const loadTasks = useCallback(async (withSpinner = false) => {
    if (withSpinner) setLoading(true);
    try {
      const list = await offlineDownloadsApi.list();
      setTasks(list.map(item => ({ ...item, key: item.id })));
    } catch (err: any) {
      messageApi.error(err?.message || t('Load failed'));
    } finally {
      if (withSpinner) setLoading(false);
    }
  }, [messageApi, t]);

  useEffect(() => {
    loadTasks(true);
    const timer = window.setInterval(() => {
      loadTasks().catch(() => {});
    }, 3000);
    return () => window.clearInterval(timer);
  }, [loadTasks]);

  const handleSelectFolder = useCallback((path: string) => {
    form.setFieldsValue({ dest_dir: path });
    setPathModalOpen(false);
  }, [form]);

  const handleSubmit = useCallback(async () => {
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      const resp = await offlineDownloadsApi.create(values);
      messageApi.success(`${t('Task submitted')}: ${resp.task_id}`);
      form.resetFields();
      await loadTasks(true);
      setCreateModalOpen(false);
    } catch (err: any) {
      if (err?.errorFields) return;
      messageApi.error(err?.message || t('Operation failed'));
    } finally {
      setSubmitting(false);
    }
  }, [form, loadTasks, messageApi, t]);

  const columns: TableColumnsType<TableRow> = useMemo(() => [
    {
      title: t('Filename'),
      dataIndex: ['meta', 'filename'],
      render: (_: any, record) => record.meta?.filename || record.task_info?.filename || '--',
    },
    {
      title: t('Stage'),
      dataIndex: ['progress', 'stage'],
      render: (_: any, record) => stageLabel(t, record.progress?.stage),
    },
    {
      title: t('Progress'),
      dataIndex: ['progress', 'percent'],
      render: (_: any, record) => {
        const percent = record.progress?.percent;
        return percent !== undefined && percent !== null ? `${percent.toFixed(1)}%` : '--';
      },
    },
    {
      title: t('Bytes'),
      render: (_: any, record) => {
        const done = record.progress?.bytes_done;
        const total = record.progress?.bytes_total;
        if (done === undefined && total === undefined) return '--';
        if (total) {
          return `${formatBytes(done)} / ${formatBytes(total)}`;
        }
        return formatBytes(done);
      },
    },
    {
      title: t('Status'),
      dataIndex: 'status',
      render: (status: TableRow['status'], record) => (
        <Space>
          {statusTag(status, t)}
          {status === 'failed' && record.error ? <Typography.Text type="danger">{record.error}</Typography.Text> : null}
        </Space>
      ),
    },
    {
      title: t('Save Path'),
      dataIndex: ['meta', 'final_path'],
      render: (value: string | undefined, record) => value || record.task_info?.dest_dir || '--',
    },
  ], [t]);

  return (
    <>
      {contextHolder}
      <PageCard
        title={t('Offline Downloads')}
        extra={
          <Button type="primary" onClick={() => { form.resetFields(); setCreateModalOpen(true); }}>
            {t('Create Offline Download')}
          </Button>
        }
      >
        <Table
          columns={columns}
          dataSource={tasks}
          loading={loading}
          pagination={false}
          locale={{ emptyText: t('No offline download tasks') }}
          rowKey="id"
          style={{ marginBottom: 0 }}
        />
      </PageCard>

      <Modal
        title={t('Create Offline Download')}
        open={createModalOpen}
        onCancel={() => { setCreateModalOpen(false); form.resetFields(); }}
        onOk={handleSubmit}
        okText={t('Start Download')}
        okButtonProps={{ loading: submitting }}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="url" label={t('URL')} rules={[{ required: true, message: t('Please input URL') }]}>
            <Input placeholder="https://example.com/file" />
          </Form.Item>
          {(() => {
            const errors = form.getFieldError('dest_dir');
            const hasError = errors.length > 0;
            return (
              <Form.Item
                label={t('Destination Folder')}
                required
                validateStatus={hasError ? 'error' : undefined}
                help={hasError ? errors[0] : undefined}
              >
                <Input.Group compact style={{ display: 'flex' }}>
                  <Form.Item
                    name="dest_dir"
                    noStyle
                    rules={[{ required: true, message: t('Select destination') }]}
                  >
                    <Input
                      readOnly
                      placeholder={t('Select destination')}
                      style={{ width: 'calc(100% - 120px)', cursor: 'pointer' }}
                      onClick={() => setPathModalOpen(true)}
                    />
                  </Form.Item>
                  <Button
                    type="default"
                    icon={<FolderOpenOutlined />}
                    onClick={() => setPathModalOpen(true)}
                    style={{ width: 120 }}
                  >
                    {t('Select Folder')}
                  </Button>
                </Input.Group>
              </Form.Item>
            );
          })()}
          <Form.Item name="filename" label={t('Filename')} rules={[{ required: true, message: t('Please input filename') }]}>
            <Input placeholder="example.zip" />
          </Form.Item>
        </Form>
      </Modal>

      <PathSelectorModal
        open={pathModalOpen}
        mode="directory"
        initialPath={form.getFieldValue('dest_dir') || '/'}
        onOk={handleSelectFolder}
        onCancel={() => setPathModalOpen(false)}
      />
    </>
  );
});

export default OfflineDownloadPage;
