import { useCallback, useEffect, useState } from 'react';
import { Form, Button, Card, Space, Spin, Empty, Alert, Select, Input, Modal, message } from 'antd';
import { vectorDBApi, type VectorDBStats, type VectorDBProviderMeta, type VectorDBCurrentConfig } from '../../../api/vectorDB';
import { useI18n } from '../../../i18n';

interface VectorDbSettingsTabProps {
  isActive: boolean;
}

const formatBytes = (bytes?: number | null) => {
  if (bytes === null || bytes === undefined) return '-';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  const precision = value >= 10 || unitIndex === 0 ? 0 : 1;
  return `${value.toFixed(precision)} ${units[unitIndex]}`;
};

const buildProviderConfigValues = (
  provider: VectorDBProviderMeta | undefined,
  existing?: Record<string, string>,
) => {
  if (!provider) return {};
  const values: Record<string, string> = {};
  const schema = provider.config_schema || [];
  schema.forEach((field) => {
    const current = existing && existing[field.key] !== undefined && existing[field.key] !== null
      ? String(existing[field.key])
      : undefined;
    if (current !== undefined) {
      values[field.key] = current;
    } else if (field.default !== undefined && field.default !== null) {
      values[field.key] = String(field.default);
    } else {
      values[field.key] = '';
    }
  });
  return values;
};

export default function VectorDbSettingsTab({ isActive }: VectorDbSettingsTabProps) {
  const [form] = Form.useForm();
  const { t } = useI18n();
  const [vectorStats, setVectorStats] = useState<VectorDBStats | null>(null);
  const [vectorStatsLoading, setVectorStatsLoading] = useState(false);
  const [vectorStatsError, setVectorStatsError] = useState<string | null>(null);
  const [vectorProviders, setVectorProviders] = useState<VectorDBProviderMeta[]>([]);
  const [vectorConfig, setVectorConfig] = useState<VectorDBCurrentConfig | null>(null);
  const [vectorConfigLoading, setVectorConfigLoading] = useState(false);
  const [vectorConfigSaving, setVectorConfigSaving] = useState(false);
  const [vectorMetaError, setVectorMetaError] = useState<string | null>(null);
  const [selectedProviderType, setSelectedProviderType] = useState<string | null>(null);

  const fetchVectorStats = useCallback(async () => {
    setVectorStatsLoading(true);
    setVectorStatsError(null);
    try {
      const data = await vectorDBApi.getStats();
      setVectorStats(data);
    } catch (e: any) {
      const msg = e?.message || t('Load failed');
      setVectorStatsError(msg);
      message.error(msg);
    } finally {
      setVectorStatsLoading(false);
    }
  }, [t]);

  const fetchVectorMeta = useCallback(async () => {
    setVectorConfigLoading(true);
    setVectorMetaError(null);
    try {
      const [providers, current] = await Promise.all([
        vectorDBApi.getProviders(),
        vectorDBApi.getConfig(),
      ]);
      setVectorProviders(providers);
      setVectorConfig(current);

      const enabled = providers.filter((item) => item.enabled);
      let nextType: string | null = current?.type ?? null;
      if (nextType && !providers.some((item) => item.type === nextType)) {
        nextType = null;
      }
      if (!nextType) {
        nextType = enabled[0]?.type ?? providers[0]?.type ?? null;
      }
      setSelectedProviderType(nextType);

      const provider = providers.find((item) => item.type === nextType);
      const configValues = buildProviderConfigValues(
        provider,
        nextType === current?.type ? current?.config : undefined,
      );
      form.setFieldsValue({ type: nextType || undefined, config: configValues });
    } catch (e: any) {
      const msg = e?.message || t('Load failed');
      setVectorMetaError(msg);
      message.error(msg);
    } finally {
      setVectorConfigLoading(false);
    }
  }, [form, t]);

  const handleProviderChange = useCallback((value: string) => {
    setSelectedProviderType(value);
    const provider = vectorProviders.find((item) => item.type === value);
    const existing = value === vectorConfig?.type ? vectorConfig?.config : undefined;
    const configValues = buildProviderConfigValues(provider, existing);
    form.setFieldsValue({ type: value, config: configValues });
  }, [form, vectorConfig, vectorProviders]);

  const handleVectorConfigSave = useCallback(async (values: { type: string; config?: Record<string, string> }) => {
    if (!values?.type) {
      return;
    }
    setVectorConfigSaving(true);
    try {
      const configPayload = Object.fromEntries(
        Object.entries(values.config || {})
          .filter(([, val]) => val !== undefined && val !== null && String(val).trim() !== '')
          .map(([key, val]) => [key, String(val)]),
      );
      const response = await vectorDBApi.updateConfig({ type: values.type, config: configPayload });
      setVectorConfig(response.config);
      setVectorStats(response.stats);
      setVectorStatsError(null);
      setSelectedProviderType(response.config.type);
      const provider = vectorProviders.find((item) => item.type === response.config.type);
      const mergedValues = buildProviderConfigValues(provider, response.config.config);
      form.setFieldsValue({ type: response.config.type, config: mergedValues });
      message.success(t('Saved successfully'));
    } catch (e: any) {
      message.error(e?.message || t('Save failed'));
    } finally {
      setVectorConfigSaving(false);
    }
  }, [form, t, vectorProviders]);

  const handleClearVectorDb = useCallback(() => {
    Modal.confirm({
      title: t('Confirm clear vector database?'),
      content: t('This will delete all collections irreversibly.'),
      okText: t('Confirm Clear'),
      okType: 'danger',
      cancelText: t('Cancel'),
      onOk: async () => {
        try {
          await vectorDBApi.clearAll();
          message.success(t('Vector database cleared'));
          await fetchVectorStats();
          await fetchVectorMeta();
        } catch (e: any) {
          message.error(e?.message || t('Clear failed'));
        }
      },
    });
  }, [fetchVectorMeta, fetchVectorStats, t]);

  useEffect(() => {
    if (!isActive) {
      return;
    }
    if (!vectorProviders.length && !vectorConfigLoading) {
      fetchVectorMeta();
    }
    if (!vectorStats && !vectorStatsLoading) {
      fetchVectorStats();
    }
  }, [
    isActive,
    fetchVectorMeta,
    fetchVectorStats,
    vectorProviders.length,
    vectorConfigLoading,
    vectorStats,
    vectorStatsLoading,
  ]);

  const vectorSectionLoading = vectorStatsLoading || vectorConfigLoading;
  const selectedProvider = vectorProviders.find(
    (item) => item.type === selectedProviderType || (!selectedProviderType && item.enabled),
  );

  return (
    <Card title={t('Vector Database Settings')} style={{ marginTop: 24 }}>
      <Space direction="vertical" size={24} style={{ width: '100%' }}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <strong>{t('Current Statistics')}</strong>
            <Button onClick={() => { fetchVectorMeta(); fetchVectorStats(); }} loading={vectorStatsLoading || vectorConfigLoading} disabled={(vectorStatsLoading || vectorConfigLoading) && !vectorStats}>
              {t('Refresh')}
            </Button>
          </div>
          {vectorSectionLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '24px 0' }}>
              <Spin />
            </div>
          ) : (
            <>
              {vectorMetaError ? (
                <Alert type="error" showIcon message={vectorMetaError} />
              ) : null}
              {vectorStats ? (
                <Space direction="vertical" size={16} style={{ width: '100%' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24 }}>
                    <div>
                      <div style={{ color: '#888' }}>{t('Collections')}</div>
                      <div style={{ fontSize: 20, fontWeight: 600 }}>{vectorStats.collection_count}</div>
                    </div>
                    <div>
                      <div style={{ color: '#888' }}>{t('Vectors')}</div>
                      <div style={{ fontSize: 20, fontWeight: 600 }}>{vectorStats.total_vectors}</div>
                    </div>
                    <div>
                      <div style={{ color: '#888' }}>{t('Database Size')}</div>
                      <div style={{ fontSize: 20, fontWeight: 600 }}>{formatBytes(vectorStats.db_file_size_bytes)}</div>
                    </div>
                    <div>
                      <div style={{ color: '#888' }}>{t('Estimated Memory')}</div>
                      <div style={{ fontSize: 20, fontWeight: 600 }}>{formatBytes(vectorStats.estimated_total_memory_bytes)}</div>
                    </div>
                  </div>
                  {vectorStats.collections.length ? (
                    <Space direction="vertical" style={{ width: '100%' }} size={16}>
                      {vectorStats.collections.map((collection) => (
                        <div key={collection.name} style={{ border: '1px solid #f0f0f0', borderRadius: 8, padding: 16 }}>
                          <Space direction="vertical" size={12} style={{ width: '100%' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                              <strong>{collection.name}</strong>
                              <span style={{ color: '#888' }}>
                                {collection.is_vector_collection && collection.dimension
                                  ? `${t('Dimension')}: ${collection.dimension}`
                                  : t('Non-vector collection')}
                              </span>
                            </div>
                            <div>{t('Vectors')}: {collection.row_count}</div>
                            {collection.is_vector_collection ? (
                              <div>{t('Estimated memory')}: {formatBytes(collection.estimated_memory_bytes)}</div>
                            ) : null}
                            {collection.indexes.length ? (
                              <Space direction="vertical" size={4} style={{ width: '100%' }}>
                                <span>{t('Indexes')}:</span>
                                <ul style={{ paddingLeft: 20, margin: 0 }}>
                                  {collection.indexes.map((index) => (
                                    <li key={`${collection.name}-${index.index_name || 'default'}`}>
                                      <span>{index.index_name || t('Unnamed index')}</span>
                                      <span>{' · '}{index.index_type || '-'}</span>
                                      <span>{' · '}{index.metric_type || '-'}</span>
                                      <span>{' · '}{t('Indexed rows')}: {index.indexed_rows}</span>
                                      <span>{' · '}{t('Pending rows')}: {index.pending_index_rows}</span>
                                      <span>{' · '}{t('Status')}: {index.state || '-'}</span>
                                    </li>
                                  ))}
                                </ul>
                              </Space>
                            ) : null}
                          </Space>
                        </div>
                      ))}
                    </Space>
                  ) : (
                    <Empty description={t('No collections')} />
                  )}
                  <div style={{ color: '#888' }}>
                    {t('Estimated memory is calculated as vectors x dimension x 4 bytes (float32).')}
                  </div>
                </Space>
              ) : vectorStatsError ? (
                <div style={{ color: '#ff4d4f' }}>{vectorStatsError}</div>
              ) : (
                <Empty description={t('No collections')} />
              )}
              <Form
                layout="vertical"
                form={form}
                onFinish={handleVectorConfigSave}
                initialValues={{ type: selectedProviderType || undefined, config: {} }}
              >
                <Form.Item
                  name="type"
                  label={t('Database Provider')}
                  rules={[{ required: true, message: t('Please select a provider') }]}
                >
                  <Select
                    size="large"
                    options={vectorProviders.map((provider) => ({
                      value: provider.type,
                      label: provider.enabled ? provider.label : `${provider.label} (${t('Coming soon')})`,
                      disabled: !provider.enabled,
                    }))}
                    onChange={handleProviderChange}
                    loading={vectorConfigLoading && !vectorProviders.length}
                  />
                </Form.Item>
                {selectedProvider?.description ? (
                  <Alert
                    type="info"
                    showIcon
                    message={t(selectedProvider.description)}
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                {selectedProvider?.config_schema?.map((field) => (
                  <Form.Item
                    key={field.key}
                    name={['config', field.key]}
                    label={t(field.label)}
                    rules={field.required ? [{ required: true, message: t('Please input {label}', { label: t(field.label) }) }] : []}
                  >
                    {field.type === 'password' ? (
                      <Input.Password size="large" placeholder={field.placeholder ? t(field.placeholder) : undefined} />
                    ) : (
                      <Input size="large" placeholder={field.placeholder ? t(field.placeholder) : undefined} />
                    )}
                  </Form.Item>
                ))}
                {selectedProvider && !selectedProvider.enabled ? (
                  <Alert
                    type="warning"
                    showIcon
                    message={t('This provider is not available yet')}
                    style={{ marginBottom: 16 }}
                  />
                ) : null}
                <Form.Item>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <Button
                      type="primary"
                      htmlType="submit"
                      loading={vectorConfigSaving}
                      block
                      disabled={!selectedProvider?.enabled}
                    >
                      {t('Save')}
                    </Button>
                    <Button
                      danger
                      htmlType="button"
                      block
                      onClick={handleClearVectorDb}
                    >
                      {t('Clear Vector DB')}
                    </Button>
                  </Space>
                </Form.Item>
              </Form>
            </>
          )}
        </Space>
      </Space>
    </Card>
  );
}
