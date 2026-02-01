import { Alert, message, Tabs, Space } from 'antd';
import { useEffect, useState } from 'react';
import PageCard from '../../components/PageCard';
import { getAllConfig, setConfig } from '../../api/config';
import { AppstoreOutlined, RobotOutlined, DatabaseOutlined, SkinOutlined, MailOutlined, CloudSyncOutlined, UserOutlined } from '@ant-design/icons';
import { useTheme } from '../../contexts/ThemeContext';
import '../../styles/settings-tabs.css';
import { useI18n } from '../../i18n';
import AppearanceSettingsTab from './components/AppearanceSettingsTab';
import AppSettingsTab from './components/AppSettingsTab';
import AuthSettingsTab from './components/AuthSettingsTab';
import AiSettingsTab from './components/AiSettingsTab';
import VectorDbSettingsTab from './components/VectorDbSettingsTab';
import EmailSettingsTab from './components/EmailSettingsTab';
import ProtocolMappingsTab from './components/ProtocolMappingsTab';

type TabKey = 'appearance' | 'app' | 'auth' | 'email' | 'ai' | 'vector-db' | 'mappings';

const TAB_KEYS: TabKey[] = ['appearance', 'app', 'auth', 'email', 'ai', 'vector-db', 'mappings'];
const DEFAULT_TAB: TabKey = 'appearance';

const isValidTab = (key?: string): key is TabKey => !!key && (TAB_KEYS as string[]).includes(key);

interface SystemSettingsPageProps {
  tabKey?: string;
  onTabNavigate?: (key: TabKey, options?: { replace?: boolean }) => void;
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

export default function SystemSettingsPage({ tabKey, onTabNavigate }: SystemSettingsPageProps) {
  const [loading, setLoading] = useState(false);
  const [config, setConfigState] = useState<Record<string, string> | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>(() =>
    isValidTab(tabKey) ? tabKey : DEFAULT_TAB
  );
  const { refreshTheme } = useTheme();
  const { t } = useI18n();

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

  const handleSave = async (values: Record<string, unknown>) => {
    setLoading(true);
    try {
      for (const [key, value] of Object.entries(values)) {
        await setConfig(key, String(value ?? ''));
      }
      message.success(t('Saved successfully'));
      const stringValues = Object.fromEntries(
        Object.entries(values).map(([key, value]) => [key, String(value ?? '')]),
      ) as Record<string, string>;
      setConfigState((prev) => ({ ...(prev ?? {}), ...stringValues }));
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

  if (loadError) {
    return (
      <PageCard title={t('System Settings')}>
        <Alert type="error" showIcon message={loadError} />
      </PageCard>
    );
  }

  if (!config) {
    return <PageCard title={t('System Settings')}><div>{t('Loading...')}</div></PageCard>;
  }

  return (
    <PageCard
      title={t('System Settings')}
    >
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <Tabs
          className="fx-settings-tabs"
          activeKey={activeTab}
          onChange={handleTabChange}
          centered
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
                  {t('App Settings')}
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
              key: 'auth',
              label: (
                <span>
                  <UserOutlined style={{ marginRight: 8 }} />
                  {t('Registration Settings')}
                </span>
              ),
              children: (
                <AuthSettingsTab
                  config={config}
                  loading={loading}
                  onSave={handleSave}
                />
              ),
            },
            {
              key: 'email',
              label: (
                <span>
                  <MailOutlined style={{ marginRight: 8 }} />
                  {t('Email Settings')}
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
                  {t('AI Settings')}
                </span>
              ),
              children: (
                <AiSettingsTab
                />
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
                <VectorDbSettingsTab isActive={activeTab === 'vector-db'} />
              ),
            },
            {
              key: 'mappings',
              label: (
                <span>
                  <CloudSyncOutlined style={{ marginRight: 8 }} />
                  {t('Protocol Mappings')}
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
      </Space>
    </PageCard>
  );
}
