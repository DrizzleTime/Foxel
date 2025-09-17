import { Form, Input, Button, message, Tabs, Space, Card, Select, Modal, Radio, InputNumber } from 'antd';
import { useEffect, useState } from 'react';
import PageCard from '../../components/PageCard';
import { getAllConfig, setConfig } from '../../api/config';
import { vectorDBApi } from '../../api/vectorDB';
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

// Theme related config keys
const THEME_KEYS = {
  MODE: 'THEME_MODE',
  PRIMARY: 'THEME_PRIMARY_COLOR',
  RADIUS: 'THEME_BORDER_RADIUS',
  TOKENS: 'THEME_CUSTOM_TOKENS',
  CSS: 'THEME_CUSTOM_CSS',
};

export default function SystemSettingsPage() {
  const [loading, setLoading] = useState(false);
  const [config, setConfigState] = useState<Record<string, string> | null>(null);
  const [activeTab, setActiveTab] = useState('appearance');
  const { refreshTheme, previewTheme } = useTheme();
  const { t } = useI18n();

  useEffect(() => {
    getAllConfig().then((data) => setConfigState(data as Record<string, string>));
  }, []);

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

  // 离开“外观设置”时，恢复后端持久化配置（取消未保存的预览）
  useEffect(() => {
    if (activeTab !== 'appearance') {
      refreshTheme();
    }
  }, [activeTab]);

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
                  <Form layout="vertical">
                    <Form.Item label={t('Database Type')}>
                      <Select
                        size="large"
                        value={'Milvus Lite'}
                        disabled
                        options={[{ value: 'Milvus Lite', label: 'Milvus Lite' }]}
                      />
                    </Form.Item>
                    <Form.Item>
                      <Button
                        danger
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
                              } catch (e: any) {
                                message.error(e.message || t('Clear failed'));
                              }
                            },
                          });
                        }}
                      >
                        {t('Clear Vector DB')}
                      </Button>
                    </Form.Item>
                  </Form>
                </Card>
              ),
            },
          ]}
        />
      </Space>
    </PageCard>
  );
}
