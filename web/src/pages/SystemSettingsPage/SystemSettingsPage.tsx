import { Form, Input, Button, message, Tabs, Space, Card, Select, Modal, Radio, InputNumber, Spin, Empty, Alert } from 'antd';
import { useEffect, useState, useCallback } from 'react';
import PageCard from '../../components/PageCard';
import { getAllConfig, setConfig } from '../../api/config';
import { vectorDBApi, type VectorDBStats, type VectorDBProviderMeta, type VectorDBCurrentConfig } from '../../api/vectorDB';
import { AppstoreOutlined, RobotOutlined, DatabaseOutlined, SkinOutlined } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';
import '../../styles/settings-tabs.css';
import { useI18n } from '../../i18n';

const APP_CONFIG_KEYS: {key: string, label: string, default?: string}[] = [
  { key: 'APP_NAME', label: 'App Name' },
  { key: 'APP_LOGO', label: 'Logo URL' },
  { key: 'APP_DOMAIN', label: 'App Domain' },
  { key: 'FILE_DOMAIN', label: 'File Domain' },
];

const VISION_CONFIG_KEYS = [
  { key: 'AI_VISION_API_URL', label: 'Vision API URL' },
  { key: 'AI_VISION_MODEL', label: 'Vision Model', default: 'Qwen/Qwen2.5-VL-32B-Instruct' },
  { key: 'AI_VISION_API_KEY', label: 'Vision API Key' },
];

const DEFAULT_EMBED_DIMENSION = 4096;
const EMBED_DIM_KEY = 'AI_EMBED_DIM';

const EMBED_CONFIG_KEYS = [
  { key: 'AI_EMBED_API_URL', label: 'Embedding API URL' },
  { key: 'AI_EMBED_MODEL', label: 'Embedding Model', default: 'Qwen/Qwen3-Embedding-8B' },
  { key: 'AI_EMBED_API_KEY', label: 'Embedding API Key' },
];

const ALL_AI_KEYS = [...VISION_CONFIG_KEYS, ...EMBED_CONFIG_KEYS, { key: EMBED_DIM_KEY, default: DEFAULT_EMBED_DIMENSION }];

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

// Theme related config keys
const THEME_KEYS = {
  MODE: 'THEME_MODE',
  PRIMARY: 'THEME_PRIMARY_COLOR',
  RADIUS: 'THEME_BORDER_RADIUS',
  TOKENS: 'THEME_CUSTOM_TOKENS',
  CSS: 'THEME_CUSTOM_CSS',
};

export default function SystemSettingsPage() {
  const [vectorConfigForm] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [config, setConfigState] = useState<Record<string, string> | null>(null);
  const [activeTab, setActiveTab] = useState('appearance');
  const [vectorStats, setVectorStats] = useState<VectorDBStats | null>(null);
  const [vectorStatsLoading, setVectorStatsLoading] = useState(false);
  const [vectorStatsError, setVectorStatsError] = useState<string | null>(null);
  const [vectorProviders, setVectorProviders] = useState<VectorDBProviderMeta[]>([]);
  const [vectorConfig, setVectorConfig] = useState<VectorDBCurrentConfig | null>(null);
  const [vectorConfigLoading, setVectorConfigLoading] = useState(false);
  const [vectorConfigSaving, setVectorConfigSaving] = useState(false);
  const [vectorMetaError, setVectorMetaError] = useState<string | null>(null);
  const [selectedProviderType, setSelectedProviderType] = useState<string | null>(null);
  const { refreshTheme, previewTheme } = useTheme();
  const { t } = useI18n();

  useEffect(() => {
    getAllConfig().then((data) => setConfigState(data as Record<string, string>));
  }, []);

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

  const buildProviderConfigValues = useCallback((provider: VectorDBProviderMeta | undefined, existing?: Record<string, string>) => {
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
  }, []);

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
      const configValues = buildProviderConfigValues(provider, nextType === current?.type ? current?.config : undefined);
      vectorConfigForm.setFieldsValue({ type: nextType || undefined, config: configValues });
    } catch (e: any) {
      const msg = e?.message || t('Load failed');
      setVectorMetaError(msg);
      message.error(msg);
    } finally {
      setVectorConfigLoading(false);
    }
  }, [buildProviderConfigValues, message, t, vectorConfigForm]);

  const handleSave = async (values: any) => {
    setLoading(true);
    try {
      for (const [key, value] of Object.entries(values)) {
        await setConfig(key, String(value ?? ''));
      }
      message.success(t('Saved successfully'));
      setConfigState({ ...config, ...values });
      // trigger theme refresh if related keys changed
      if (Object.keys(values).some(k => Object.values(THEME_KEYS).includes(k))) {
        await refreshTheme();
      }
    } catch (e: any) {
      message.error(e.message || t('Save failed'));
    }
    setLoading(false);
  };

  const handleProviderChange = useCallback((value: string) => {
    setSelectedProviderType(value);
    const provider = vectorProviders.find((item) => item.type === value);
    const existing = value === vectorConfig?.type ? vectorConfig?.config : undefined;
    const configValues = buildProviderConfigValues(provider, existing);
    vectorConfigForm.setFieldsValue({ type: value, config: configValues });
  }, [vectorProviders, vectorConfig, buildProviderConfigValues, vectorConfigForm]);

  const handleVectorConfigSave = useCallback(async (values: { type: string; config?: Record<string, string> }) => {
    if (!values?.type) {
      return;
    }
    setVectorConfigSaving(true);
    try {
      const configPayload = Object.fromEntries(
        Object.entries(values.config || {}).filter(([, val]) => val !== undefined && val !== null && String(val).trim() !== '')
          .map(([key, val]) => [key, String(val)])
      );
      const response = await vectorDBApi.updateConfig({ type: values.type, config: configPayload });
      setVectorConfig(response.config);
      setVectorStats(response.stats);
      setVectorStatsError(null);
      setSelectedProviderType(response.config.type);
      const provider = vectorProviders.find((item) => item.type === response.config.type);
      const mergedValues = buildProviderConfigValues(provider, response.config.config);
      vectorConfigForm.setFieldsValue({ type: response.config.type, config: mergedValues });
      message.success(t('Saved successfully'));
    } catch (e: any) {
      message.error(e?.message || t('Save failed'));
    } finally {
      setVectorConfigSaving(false);
    }
  }, [buildProviderConfigValues, message, t, vectorConfigForm, vectorProviders]);

  // 离开“外观设置”时，恢复后端持久化配置（取消未保存的预览）
  useEffect(() => {
    if (activeTab !== 'appearance') {
      refreshTheme();
    }
  }, [activeTab]);

  useEffect(() => {
    if (activeTab === 'vector-db') {
      if (!vectorProviders.length && !vectorConfigLoading) {
        fetchVectorMeta();
      }
      if (!vectorStats && !vectorStatsLoading) {
        fetchVectorStats();
      }
    }
  }, [
    activeTab,
    fetchVectorMeta,
    fetchVectorStats,
    vectorProviders.length,
    vectorConfigLoading,
    vectorStats,
    vectorStatsLoading,
  ]);

  const selectedProvider = vectorProviders.find((item) => item.type === selectedProviderType || (!selectedProviderType && item.enabled));

  if (!config) {
    return <PageCard title={t('System Settings')}><div>{t('Loading...')}</div></PageCard>;
  }

  return (
    <PageCard
      title={t('System Settings')}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={32}>
        <Tabs
          className="fx-settings-tabs"
          activeKey={activeTab}
          onChange={setActiveTab}
          centered
          tabPosition="left"
          items={[
            {
              key: 'appearance',
              label: (
                <span>
                  <SkinOutlined style={{ marginRight: 8 }} />
                  {t('Appearance Settings')}
                </span>
              ),
              children: (
                <Form
                  layout="vertical"
                  initialValues={{
                    [THEME_KEYS.MODE]: config[THEME_KEYS.MODE] ?? 'light',
                    [THEME_KEYS.PRIMARY]: config[THEME_KEYS.PRIMARY] ?? '#111111',
                    [THEME_KEYS.RADIUS]: Number(config[THEME_KEYS.RADIUS] ?? '10'),
                    [THEME_KEYS.TOKENS]: config[THEME_KEYS.TOKENS] ?? '',
                    [THEME_KEYS.CSS]: config[THEME_KEYS.CSS] ?? '',
                  }}
                  onValuesChange={(_, all) => {
                    try {
                      const tokens = all[THEME_KEYS.TOKENS] ? JSON.parse(all[THEME_KEYS.TOKENS]) : undefined;
                      previewTheme({
                        mode: all[THEME_KEYS.MODE],
                        primaryColor: all[THEME_KEYS.PRIMARY],
                        borderRadius: typeof all[THEME_KEYS.RADIUS] === 'number' ? all[THEME_KEYS.RADIUS] : undefined,
                        customTokens: tokens,
                        customCSS: all[THEME_KEYS.CSS],
                      });
                    } catch {
                      // JSON 不合法时忽略 tokens 预览，其他项仍然生效
                      previewTheme({
                        mode: all[THEME_KEYS.MODE],
                        primaryColor: all[THEME_KEYS.PRIMARY],
                        borderRadius: typeof all[THEME_KEYS.RADIUS] === 'number' ? all[THEME_KEYS.RADIUS] : undefined,
                        customCSS: all[THEME_KEYS.CSS],
                      });
                    }
                  }}
                  onFinish={async (vals) => {
                    // Validate JSON if provided
                    if (vals[THEME_KEYS.TOKENS]) {
                      try { JSON.parse(vals[THEME_KEYS.TOKENS]); }
                      catch { return message.error(t('Advanced tokens must be valid JSON')); }
                    }
                    await handleSave(vals);
                  }}
                  style={{ marginTop: 24 }}
                  key={'appearance-' + JSON.stringify(config)}
                >
                  <Card title={t('Theme')}>
                    <Form.Item name={THEME_KEYS.MODE} label={t('Theme Mode')}>
                      <Radio.Group buttonStyle="solid">
                        <Radio.Button value="light">{t('Light')}</Radio.Button>
                        <Radio.Button value="dark">{t('Dark')}</Radio.Button>
                        <Radio.Button value="system">{t('Follow System')}</Radio.Button>
                      </Radio.Group>
                    </Form.Item>
                    <Form.Item name={THEME_KEYS.PRIMARY} label={t('Primary Color')}>
                      <Input type="color" size="large" />
                    </Form.Item>
                    <Form.Item name={THEME_KEYS.RADIUS} label={t('Border Radius')}>
                      <InputNumber min={0} max={24} style={{ width: '100%' }} />
                    </Form.Item>
                  </Card>
                  <Card title={t('Advanced')} style={{ marginTop: 24 }}>
                    <Form.Item name={THEME_KEYS.TOKENS} label={t('Override AntD Tokens (JSON)')} tooltip={t('e.g. {"colorText": "#222"}') }>
                      <Input.TextArea autoSize={{ minRows: 4 }} placeholder='{ "colorText": "#222" }' />
                    </Form.Item>
                    <Form.Item name={THEME_KEYS.CSS} label={t('Custom CSS')}>
                      <Input.TextArea autoSize={{ minRows: 6 }} placeholder={":root{ }\n/* CSS */"} />
                    </Form.Item>
                  </Card>
                  <Form.Item style={{ marginTop: 24 }}>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      {t('Save')}
                    </Button>
                  </Form.Item>
                </Form>
              )
            },
            {
              key: 'app',
              label: (
                <span>
                  <AppstoreOutlined style={{ marginRight: 8 }} />
                  {t('App Settings')}
                </span>
              ),
              children: (
                <Form
                  layout="vertical"
                  initialValues={{
                    ...Object.fromEntries(APP_CONFIG_KEYS.map(({ key, default: def }) => [key, config[key] ?? def ?? ''])),
                  }}
                  onFinish={handleSave}
                  style={{ marginTop: 24 }}
                  key={JSON.stringify(config)}
                >
                  {APP_CONFIG_KEYS.map(({ key, label }) => (
                    <Form.Item key={key} name={key} label={t(label)}>
                      <Input size="large" />
                    </Form.Item>
                  ))}
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      {t('Save')}
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'ai',
              label: (
                <span>
                  <RobotOutlined style={{ marginRight: 8 }} />
                  {t('AI Settings')}
                </span>
              ),
              children: (
                <Form
                  layout="vertical"
                  initialValues={{
                    ...Object.fromEntries(ALL_AI_KEYS.map(({ key, default: def }) => [key, key === EMBED_DIM_KEY
                      ? Number(config[key] ?? def ?? DEFAULT_EMBED_DIMENSION)
                      : config[key] ?? def ?? ''])),
                  }}
                  onFinish={async (vals) => {
                    const currentDim = Number(config[EMBED_DIM_KEY] ?? DEFAULT_EMBED_DIMENSION);
                    const nextDim = Number(vals[EMBED_DIM_KEY] ?? DEFAULT_EMBED_DIMENSION);
                    if (currentDim !== nextDim) {
                      Modal.confirm({
                        title: t('Confirm embedding dimension change'),
                        content: t('Changing the embedding dimension will clear the vector database automatically. You will need to rebuild indexes afterwards. Continue?'),
                        okText: t('Confirm'),
                        cancelText: t('Cancel'),
                        onOk: async () => {
                          await handleSave(vals);
                        },
                      });
                      return;
                    }
                    await handleSave(vals);
                  }}
                  style={{ marginTop: 24 }}
                  key={JSON.stringify(config)}
                >
                  <Card title={t('Vision Model')} style={{ marginBottom: 24 }}>
                    {VISION_CONFIG_KEYS.map(({ key, label }) => (
                      <Form.Item key={key} name={key} label={t(label)}>
                        <Input size="large" />
                      </Form.Item>
                    ))}
                  </Card>
                  <Card title={t('Embedding Model')}>
                    {EMBED_CONFIG_KEYS.map(({ key, label }) => (
                      <Form.Item key={key} name={key} label={t(label)}>
                        <Input size="large" />
                      </Form.Item>
                    ))}
                    <Form.Item name={EMBED_DIM_KEY} label={t('Embedding Dimension')}>
                      <InputNumber min={1} max={32768} style={{ width: '100%' }} />
                    </Form.Item>
                  </Card>
                  <Form.Item style={{ marginTop: 24 }}>
                    <Button type="primary" htmlType="submit" loading={loading} block>
                      {t('Save')}
                    </Button>
                  </Form.Item>
                </Form>
              ),
            },
            {
              key: 'vector-db',
              label: (
                <span>
                  <DatabaseOutlined style={{ marginRight: 8 }} />
                  {t('Vector Database')}
                </span>
              ),
              children: (
                <Card title={t('Vector Database Settings')} style={{ marginTop: 24 }}>
                  <Space direction="vertical" size={24} style={{ width: '100%' }}>
                    <Space direction="vertical" size={16} style={{ width: '100%' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                        <strong>{t('Current Statistics')}</strong>
                        <Button onClick={() => { fetchVectorMeta(); fetchVectorStats(); }} loading={vectorStatsLoading || vectorConfigLoading} disabled={(vectorStatsLoading || vectorConfigLoading) && !vectorStats}>
                          {t('Refresh')}
                        </Button>
                      </div>
                      {vectorMetaError ? (
                        <Alert type="error" showIcon message={vectorMetaError} />
                      ) : null}
                      {vectorStatsLoading && !vectorStats ? (
                        <Spin />
                      ) : vectorStats ? (
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
                    </Space>
                    {vectorConfigLoading && !vectorProviders.length ? (
                      <Spin />
                    ) : (
                      <Form
                        layout="vertical"
                        form={vectorConfigForm}
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
                              onClick={() => {
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
                                      message.error(e.message || t('Clear failed'));
                                    }
                                  },
                                });
                              }}
                            >
                              {t('Clear Vector DB')}
                            </Button>
                          </Space>
                        </Form.Item>
                      </Form>
                    )}
                  </Space>
                </Card>
              ),
            },
          ]}
        />
      </Space>
    </PageCard>
  );
}
