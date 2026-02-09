import { memo, useState, useEffect, useCallback } from 'react';
import { Table, Button, Space, Drawer, Form, Input, Switch, message, Typography, Popconfirm, Select } from 'antd';
import PageCard from '../components/PageCard';
import { tasksApi, type AutomationTask } from '../api/tasks';
import { processorsApi, type ProcessorTypeMeta } from '../api/processors';
import { ProcessorConfigForm } from '../components/ProcessorConfigForm';
import { useI18n } from '../i18n';
import PathSelectorModal from '../components/PathSelectorModal';

const TasksPage = memo(function TasksPage() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<AutomationTask[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AutomationTask | null>(null);
  const [form] = Form.useForm();
  const [availableProcessors, setAvailableProcessors] = useState<ProcessorTypeMeta[]>([]);
  const { t } = useI18n();
  const [pathPickerField, setPathPickerField] = useState<'path_prefix' | 'cron_path' | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const [list, processors] = await Promise.all([
        tasksApi.list(),
        processorsApi.list()
      ]);
      setData(list);
      setAvailableProcessors(processors);
    } catch (e: any) {
      message.error(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      event: 'file_written',
      enabled: true,
      processor_config: {},
      trigger_config: {}
    });
    setOpen(true);
  };

  const openEdit = (rec: AutomationTask) => {
    setEditing(rec);
    form.resetFields();
    form.setFieldsValue({
      ...rec,
      processor_config: rec.processor_config || {},
      trigger_config: rec.trigger_config || {}
    });
    setOpen(true);
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      const triggerConfig = { ...(values.trigger_config || {}) };
      if (values.event === 'cron') {
        delete triggerConfig.path_prefix;
        delete triggerConfig.filename_regex;
      } else {
        delete triggerConfig.cron_expr;
        delete triggerConfig.path;
      }
      const body = { ...values, trigger_config: triggerConfig };
      setLoading(true);
      if (editing) {
        await tasksApi.update(editing.id, body);
        message.success('更新成功');
      } else {
        await tasksApi.create(body);
        message.success('创建成功');
      }
      setOpen(false);
      setEditing(null);
      fetchList();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || '操作失败');
    } finally {
      setLoading(false);
    }
  };

  const doDelete = async (rec: AutomationTask) => {
    try {
      await tasksApi.remove(rec.id);
      message.success('已删除');
      fetchList();
    } catch (e: any) {
      message.error(e.message || '删除失败');
    }
  };

  const toggleEnabled = async (rec: AutomationTask, enabled: boolean) => {
    setEditing(rec);
    setLoading(true);
    try {
      await tasksApi.update(rec.id, { enabled });
      message.success('状态已更新');
      fetchList();
    } catch (e: any) {
      message.error(e.message || '更新失败');
    } finally {
      setEditing(null);
      setLoading(false);
    }
  };

  const columns = [
    { title: t('Name'), dataIndex: 'name' },
    { title: t('Trigger Event'), dataIndex: 'event', width: 120 },
    { title: t('Processor'), dataIndex: 'processor_type', width: 180 },
    {
      title: t('Enabled'), dataIndex: 'enabled', width: 80, render: (v: boolean, rec: AutomationTask) => <Switch
        checked={v}
        size="small"
        loading={loading && editing?.id === rec.id}
        onChange={(checked) => toggleEnabled(rec, checked)}
      />
    },
    {
      title: t('Actions'),
      width: 160,
      render: (_: any, rec: AutomationTask) => (
        <Space size="small">
          <Button size="small" onClick={() => openEdit(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => doDelete(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const selectedProcessor = Form.useWatch('processor_type', form);
  const currentProcessorMeta = availableProcessors.find(p => p.type === selectedProcessor);
  const selectedEvent = Form.useWatch('event', form);
  const watchedPathPrefix = Form.useWatch(['trigger_config', 'path_prefix'], form);
  const watchedCronPath = Form.useWatch(['trigger_config', 'path'], form);
  const isCron = selectedEvent === 'cron';


  return (
    <PageCard
      title={t('Automation Tasks')}
      extra={
        <Space>
          <Button onClick={fetchList} loading={loading}>{t('Refresh')}</Button>
          <Button type="primary" onClick={openCreate}>{t('Create Task')}</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={data}
        columns={columns as any}
        loading={loading}
        pagination={false}
        style={{ marginBottom: 0 }}
      />
      <Drawer
        title={editing ? `${t('Edit Task')}: ${editing.name}` : t('Create Automation Task')}
        width={480}
        open={open}
        onClose={() => { setOpen(false); setEditing(null); setPathPickerField(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setOpen(false); setEditing(null); setPathPickerField(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submit} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label={t('Task Name')} rules={[{ required: true }]}> 
            <Input />
          </Form.Item>
          <Form.Item name="event" label={t('Trigger Event')} rules={[{ required: true }]}> 
            <Select options={[ 
              { value: 'file_written', label: t('File Written') }, 
              { value: 'file_deleted', label: t('File Deleted') },
              { value: 'cron', label: t('Scheduled') },
            ]} />
          </Form.Item>
          {isCron ? (
            <>
              <Typography.Title level={5} style={{ marginTop: 8, fontSize: 14 }}>{t('Schedule')}</Typography.Title>
              <Form.Item
                name={['trigger_config', 'cron_expr']}
                label={t('Cron Expression')}
                rules={[{ required: true }]}
              >
                <Input placeholder="*/5 * * * * *" />
              </Form.Item>
              <Form.Item
                name={['trigger_config', 'path']}
                label={t('Target Path')}
                rules={[{ required: true }]}
              >
                <Input
                  placeholder="/images"
                  addonAfter={<Button size="small" onClick={() => setPathPickerField('cron_path')}>{t('Select')}</Button>}
                />
              </Form.Item>
            </>
          ) : (
            <>
              <Typography.Title level={5} style={{ marginTop: 8, fontSize: 14 }}>{t('Matching Rules')}</Typography.Title>
              <Form.Item name={['trigger_config', 'path_prefix']} label={t('Path Prefix (optional)')}>
                <Input
                  placeholder="/images/screenshots"
                  addonAfter={<Button size="small" onClick={() => setPathPickerField('path_prefix')}>{t('Select')}</Button>}
                />
              </Form.Item>
              <Form.Item name={['trigger_config', 'filename_regex']} label={t('Filename Regex (optional)')}>
                <Input placeholder=".*\\.png$" />
              </Form.Item>
            </>
          )}
          <Form.Item name="enabled" label={t('Enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Typography.Title level={5} style={{ marginTop: 8, fontSize: 14 }}>{t('Action')}</Typography.Title>
          <Form.Item name="processor_type" label={t('Processor')} rules={[{ required: true }]}>
            <Select
              placeholder={t('Select a processor')}
              options={availableProcessors.map(p => ({ value: p.type, label: `${p.name} (${p.type})` }))}
            />
          </Form.Item>
          <ProcessorConfigForm
            processorMeta={currentProcessorMeta}
            form={form}
            configPath={['processor_config']}
          />
        </Form>
      </Drawer>
      <PathSelectorModal
        open={!!pathPickerField}
        mode={pathPickerField === 'cron_path' ? 'any' : 'directory'}
        initialPath={(pathPickerField === 'cron_path' ? watchedCronPath : watchedPathPrefix) || '/'}
        onCancel={() => setPathPickerField(null)}
        onOk={(p) => {
          if (pathPickerField === 'cron_path') {
            form.setFieldValue(['trigger_config', 'path'], p);
          } else if (pathPickerField === 'path_prefix') {
            form.setFieldValue(['trigger_config', 'path_prefix'], p);
          }
          setPathPickerField(null);
        }}
      />
    </PageCard>
  );
});

export default TasksPage;
