import { Alert, message, Tabs, Modal } from 'antd';
import { useEffect, useState } from 'react';
import { getAllConfig, setConfig } from '../../api/config';
import { ApiOutlined, AppstoreOutlined, RobotOutlined, DatabaseOutlined, SkinOutlined, MailOutlined, CloudSyncOutlined, CloseOutlined } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';
import '../../styles/settings-tabs.css';
import { useI18n } from '../../i18n';
import useResponsive from '../../hooks/useResponsive';
import AppearanceSettingsTab from './components/AppearanceSettingsTab';
import AppSettingsTab from './components/AppSettingsTab';
import AiSettingsTab from './components/AiSettingsTab';
import VectorDbSettingsTab from './components/VectorDbSettingsTab';
import EmailSettingsTab from './components/EmailSettingsTab';
import ProtocolMappingsTab from './components/ProtocolMappingsTab';
import McpSettingsTab from './components/McpSettingsTab';

type TabKey = 'appearance' | 'app' | 'email' | 'ai' | 'mcp' | 'vector-db' | 'mappings';

const TAB_KEYS: TabKey[] = ['appearance', 'app', 'email', 'ai', 'mcp', 'vector-db', 'mappings'];
const DEFAULT_TAB: TabKey = 'appearance';
const TAB_TITLES: Record<TabKey, string> = {
  appearance: 'Appearance',
  app: 'System',
  email: 'Email',
  ai: 'LLM',
  mcp: 'MCP',
  'vector-db': 'Database',
  mappings: 'Mappings',
};

const isValidTab = (key?: string): key is TabKey => !!key && (TAB_KEYS as string[]).includes(key);

interface SystemSettingsPageProps {
  tabKey?: string;
  onTabNavigate?: (key: TabKey, options?: { replace?: boolean }) => void;
  onClose?: () => void;
}

const APP_CONFIG_KEYS: { key: string, label: string, default?: string }[] = [
  { key: 'APP_NAME', label: 'App Name' },
  { key: 'APP_LOGO', label: 'Logo URL' },
  { key: 'APP_FAVICON', label: 'Favicon URL', default: '/logo.svg' },
  { key: 'APP_DOMAIN', label: 'App Domain' },
  { key: 'FILE_DOMAIN', label: 'File Domain' },
];

// Theme related config keys
const THEME_KEYS = {
  MODE: 'THEME_MODE',
  PRIMARY: 'THEME_PRIMARY_COLOR',
  RADIUS: 'THEME_BORDER_RADIUS',
  TOKENS: 'THEME_CUSTOM_TOKENS',
  CSS: 'THEME_CUSTOM_CSS',
};

const CONFIG_DEFAULTS: Record<string, string> = {
  ...Object.fromEntries(APP_CONFIG_KEYS.map(({ key, default: def }) => [key, def ?? ''])),
  APP_DEFAULT_LANGUAGE: 'zh',
  AUTH_ALLOW_REGISTER: 'false',
  AUTH_DEFAULT_REGISTER_ROLE_ID: '',
  DEFAULT_FILE_VIEW_MODE: 'grid',
  [THEME_KEYS.MODE]: 'light',
  [THEME_KEYS.PRIMARY]: '#111111',
  [THEME_KEYS.RADIUS]: '10',
  [THEME_KEYS.TOKENS]: '',
  [THEME_KEYS.CSS]: '',
  WEBDAV_MAPPING_ENABLED: '1',
  S3_MAPPING_ENABLED: '1',
  S3_MAPPING_BUCKET: 'foxel',
  S3_MAPPING_REGION: '',
  S3_MAPPING_BASE_PATH: '/',
  S3_MAPPING_ACCESS_KEY: '',
  S3_MAPPING_SECRET_KEY: '',
  EMAIL_CONFIG: '',
  EMAIL_PASSWORD_RESET_TEMPLATE: '',
  MCP_ENABLED: '1',
};

const stringifyConfigValue = (value: unknown) => String(value ?? '');

export default function SystemSettingsPage({ tabKey, onTabNavigate, onClose }: SystemSettingsPageProps) {
  const [loading, setLoading] = useState(false);
  const [config, setConfigState] = useState<Record<string, string> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>(() =>
    isValidTab(tabKey) ? tabKey : DEFAULT_TAB
  );
  const { refreshTheme } = useTheme();
  const { t } = useI18n();
  const { isMobile } = useResponsive();

  useEffect(() => {
    getAllConfig()
      .then((data) => {
        setLoadError(null);
        setConfigState(data as Record<string, string>);
      })
      .catch((e: any) => {
        setLoadError(e?.message || t('Load failed'));
        setConfigState({});
      });
  }, [t]);

  const handleSave = async (values: Record<string, unknown>): Promise<boolean> => {
    setLoading(true);
    try {
      const currentConfig = config ?? {};
      const changedValues = Object.fromEntries(
        Object.entries(values)
          .map(([key, value]) => [key, stringifyConfigValue(value)] as const)
          .filter(([key, value]) => value !== (currentConfig[key] ?? CONFIG_DEFAULTS[key] ?? '')),
      ) as Record<string, string>;

      for (const [key, value] of Object.entries(changedValues)) {
        await setConfig(key, value);
      }

      message.success(t('Saved successfully'));
      setConfigState((prev) => ({ ...(prev ?? {}), ...changedValues }));
      // trigger theme refresh if related keys changed
      if (Object.keys(changedValues).some(k => Object.values(THEME_KEYS).includes(k))) {
        await refreshTheme();
      }
      return true;
    } catch (e: any) {
      message.error(e.message || t('Save failed'));
      return false;
    } finally {
      setLoading(false);
    }
  };

  // 离开“外观设置”时，恢复后端持久化配置（取消未保存的预览）
  useEffect(() => {
    if (!isValidTab(tabKey)) {
      setActiveTab((prev) => (prev === DEFAULT_TAB ? prev : DEFAULT_TAB));
      if (tabKey !== DEFAULT_TAB) {
        onTabNavigate?.(DEFAULT_TAB, { replace: true });
      }
      return;
    }
    setActiveTab((prev) => (prev === tabKey ? prev : tabKey));
  }, [tabKey, onTabNavigate]);

  useEffect(() => {
    if (activeTab !== 'appearance') {
      refreshTheme();
    }
  }, [activeTab, refreshTheme]);

  const handleTabChange = (key: string) => {
    const nextKey: TabKey = isValidTab(key) ? key : DEFAULT_TAB;
    if (nextKey !== activeTab) {
      setActiveTab(nextKey);
    }
    onTabNavigate?.(nextKey);
  };

  return (
    <Modal
      open
      onCancel={onClose}
      closeIcon={<CloseOutlined />}
      title={
        <div className="fx-settings-modal-heading">
          <span className="fx-settings-modal-title">{t('System Settings')}</span>
          <span className="fx-settings-modal-section-title">{t(TAB_TITLES[activeTab])}</span>
        </div>
      }
      footer={null}
      width={isMobile ? 'calc(100vw - 24px)' : 1180}
      style={{ maxWidth: 'calc(100vw - 24px)' }}
      centered
      destroyOnHidden={false}
      className="fx-settings-modal"
      styles={{
        body: { padding: 0, overflow: 'hidden' },
        container: { padding: 0, overflow: 'hidden' },
      }}
    >
      {loadError ? (
        <div className="fx-settings-modal-message"><Alert type="error" showIcon message={loadError} /></div>
      ) : !config ? (
        <div className="fx-settings-modal-message">{t('Loading...')}</div>
      ) : (
        <Tabs
          className="fx-settings-tabs"
          classNames={{ body: 'fx-settings-body', content: 'fx-settings-pane' }}
          tabPlacement={isMobile ? 'top' : 'start'}
          activeKey={activeTab}
          onChange={handleTabChange}
          centered={false}
          items={[
            {
              key: 'appearance',
              label: (
                <span>
                  <SkinOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.appearance)}
                </span>
              ),
              children: (
                <AppearanceSettingsTab
                  config={config}
                  loading={loading}
                  onSave={handleSave}
                  themeKeys={THEME_KEYS}
                />
              )
            },
            {
              key: 'app',
              label: (
                <span>
                  <AppstoreOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.app)}
                </span>
              ),
              children: (
                <AppSettingsTab
                  config={config}
                  loading={loading}
                  onSave={handleSave}
                  configKeys={APP_CONFIG_KEYS}
                />
              ),
            },
            {
              key: 'email',
              label: (
                <span>
                  <MailOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.email)}
                </span>
              ),
              children: (
                <EmailSettingsTab
                  config={config}
                  loading={loading}
                  onSave={handleSave}
                />
              ),
            },
            {
              key: 'ai',
              label: (
                <span>
                  <RobotOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.ai)}
                </span>
              ),
              children: (
                <AiSettingsTab
                />
              ),
            },
            {
              key: 'mcp',
              label: (
                <span>
                  <ApiOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.mcp)}
                </span>
              ),
              children: <McpSettingsTab config={config} loading={loading} onSave={handleSave} />,
            },
            {
              key: 'vector-db',
              label: (
                <span>
                  <DatabaseOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES['vector-db'])}
                </span>
              ),
              children: (
                <VectorDbSettingsTab isActive={activeTab === 'vector-db'} />
              ),
            },
            {
              key: 'mappings',
              label: (
                <span>
                  <CloudSyncOutlined style={{ marginRight: 8 }} />
                  {t(TAB_TITLES.mappings)}
                </span>
              ),
              children: (
                <ProtocolMappingsTab
                  config={config}
                  loading={loading}
                  onSave={handleSave}
                />
              ),
            },
          ]}
        />
      )}
    </Modal>
  );
}
