import { memo, useState, useEffect, useCallback } from 'react';
import { Table, Button, Space, Drawer, Form, Input, Switch, message, Typography, Popconfirm, Select } from 'antd';
import PageCard from '../components/PageCard';
import { adaptersApi, type AdapterItem } from '../api/client';
import { useI18n } from '../i18n';


interface AdapterTypeField {
  key: string;
  label: string;
  type: 'string' | 'password' | 'number';
  required?: boolean;
  placeholder?: string;
  default?: any;
}
interface AdapterTypeMeta {
  type: string;
  name: string;
  config_schema: AdapterTypeField[];
}

const AdaptersPage = memo(function AdaptersPage() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<AdapterItem[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AdapterItem | null>(null);
  const [form] = Form.useForm();
  const [availableTypes, setAvailableTypes] = useState<AdapterTypeMeta[]>([]);
  const { t } = useI18n();

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const [list, types] = await Promise.all([
        adaptersApi.list(),
        adaptersApi.available()
      ]);
      setData(list);
      setAvailableTypes(types);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchList(); }, [fetchList]);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    const defaultType = availableTypes[0]?.type || 'local';
    const typeMeta = availableTypes.find(t => t.type === defaultType);
    const cfgDefaults: Record<string, any> = {};
    typeMeta?.config_schema.forEach(f => {
      if (f.default !== undefined) cfgDefaults[f.key] = f.default;
    });
    form.setFieldsValue({
      name: '',
      type: defaultType,
      path: '/',
      sub_path: '',
      enabled: true,
      config: cfgDefaults
    });
    setOpen(true);
  };

  const openEdit = (rec: AdapterItem) => {
    setEditing(rec);
    form.resetFields();
    form.setFieldsValue({
      name: rec.name,
      type: rec.type,
      path: rec.path || '/',
      sub_path: rec.sub_path || '',
      enabled: rec.enabled,
      config: rec.config || {}
    });
    setOpen(true);
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      const cfg = values.config || {};
      const typeMeta = availableTypes.find(t => t.type === values.type);
      const miss: string[] = [];
      typeMeta?.config_schema.forEach(f => {
        if (f.required && (cfg[f.key] === undefined || cfg[f.key] === null || cfg[f.key] === '')) {
          miss.push(f.label || f.key);
        }
      });
      if (miss.length) {
        message.error(t('Missing required config:') + ' ' + miss.join(', '));
        return;
      }
      const body = {
        name: values.name.trim(),
        type: values.type,
        path: values.path || '/',
        sub_path: values.sub_path?.trim() || null,
        enabled: values.enabled,
        config: cfg
      };
      setLoading(true);
      if (editing) {
        await adaptersApi.update(editing.id, body as any);
        message.success(t('Updated successfully'));
      } else {
        await adaptersApi.create(body as any);
        message.success(t('Created successfully'));
      }
      setOpen(false);
      setEditing(null);
      fetchList();
    } catch (e: any) {
      if (e?.errorFields) return; // 表单校验
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  const doDelete = async (rec: AdapterItem) => {
    try {
      await adaptersApi.remove(rec.id);
      message.success(t('Deleted'));
      fetchList();
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  const handleToggleEnabled = async (rec: AdapterItem, checked: boolean) => {
    try {
      setLoading(true);
      await adaptersApi.update(rec.id, { ...rec, enabled: checked });
      message.success(t('Status updated'));
      fetchList();
    } catch (e: any) {
      message.error(e.message || t('Update failed'));
    } finally {
      setLoading(false);
    }
  };

  const columns = [
    { title: t('Name'), dataIndex: 'name' },
    { title: t('Type'), dataIndex: 'type', width: 100 },
    { title: t('Mount Path'), dataIndex: 'path', width: 140, render: (v: string) => v || '-' },
    { title: t('Sub Path'), dataIndex: 'sub_path', width: 140, render: (v: string) => v || '-' },
    {
      title: t('Enabled'),
      dataIndex: 'enabled',
      width: 80,
      render: (v: boolean, rec: AdapterItem) => (
        <Switch
          checked={v}
          size="small"
          loading={loading}
          onChange={checked => handleToggleEnabled(rec, checked)}
        />
      )
    },
    {
      title: t('Actions'),
      width: 160,
      render: (_: any, rec: AdapterItem) => (
        <Space size="small">
          <Button size="small" onClick={() => openEdit(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => doDelete(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      )
    }
  ];

  const selectedType = Form.useWatch('type', form);
  const currentTypeMeta = availableTypes.find(t => t.type === selectedType);

  function renderConfigFields() {
    if (!currentTypeMeta) return <Typography.Text type="secondary">{t('No config fields')}</Typography.Text>;
    return currentTypeMeta.config_schema.map(field => {
      const rules = field.required ? [{ required: true, message: t('Please input {label}', { label: field.label }) }] : [];
      let inputNode: any = <Input placeholder={field.placeholder} />;
      if (field.type === 'password') inputNode = <Input.Password placeholder={field.placeholder} />;
      if (field.type === 'number') inputNode = <Input type="number" placeholder={field.placeholder} />;
      return (
        <Form.Item
          key={field.key}
          name={['config', field.key]}
          label={t(field.label)}
          rules={rules}
        >
          {inputNode}
        </Form.Item>
      );
    });
  }

  return (
    <PageCard
      title={t('Storage Adapters')}
      extra={
        <Space>
          <Button onClick={fetchList} loading={loading}>{t('Refresh')}</Button>
          <Button type="primary" onClick={openCreate}>{t('Create Adapter')}</Button>
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
        title={editing ? `${t('Edit')}: ${editing.name}` : t('Create Adapter')}
        width={480}
        open={open}
        onClose={() => { setOpen(false); setEditing(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setOpen(false); setEditing(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submit} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ enabled: true }}
        >
          <Form.Item name="name" label={t('Name')} rules={[{ required: true, message: t('Please input {label}', { label: t('Name') }) }]}>
            <Input placeholder={t('Unique name')} />
          </Form.Item>
          <Form.Item name="type" label={t('Type')} rules={[{ required: true }]}>
            <Select
              placeholder={t('Select adapter type')}
              options={availableTypes.map(t => ({ value: t.type, label: `${t.name} (${t.type})` }))}
              onChange={() => {
                const t = availableTypes.find(v => v.type === form.getFieldValue('type'));
                const cfgDefaults: Record<string, any> = {};
                t?.config_schema.forEach(f => {
                  if (f.default !== undefined) cfgDefaults[f.key] = f.default;
                });
                form.setFieldsValue({ config: cfgDefaults });
              }}
            />
          </Form.Item>
          <Form.Item name="path" label={t('Mount Path')} rules={[{ required: true, message: t('Please input {label}', { label: t('Mount Path') }) }]}>
            <Input placeholder={t('/ or /drive')} />
          </Form.Item>
          <Form.Item name="sub_path" label={t('Sub Path (optional)')}>
            <Input placeholder={t('Sub directory inside adapter')} />
          </Form.Item>
          <Form.Item name="enabled" label={t('Enabled')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <Typography.Title level={5} style={{ marginTop: 8, fontSize: 14 }}>{t('Adapter Config')}</Typography.Title>
          {renderConfigFields()}
        </Form>
      </Drawer>
    </PageCard>
  );
});

export default AdaptersPage;
