import { useEffect, useMemo, useState } from 'react';
import { Card, Descriptions, Space, Switch, Typography } from 'antd';
import { useI18n } from '../../../i18n';

interface ProtocolMappingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
}

const WEBDAV_KEY = 'WEBDAV_MAPPING_ENABLED';

const truthy = new Set(['1', 'true', 'yes', 'on']);

export default function ProtocolMappingsTab({ config, loading, onSave }: ProtocolMappingsTabProps) {
  const { t } = useI18n();
  const [webdavEnabled, setWebdavEnabled] = useState(() => truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
  const [webdavSaving, setWebdavSaving] = useState(false);

  useEffect(() => {
    setWebdavEnabled(truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
  }, [config]);

  const webdavEndpoint = useMemo(() => {
    const configured = (config.APP_DOMAIN ?? '').trim();
    if (configured) {
      const hasProtocol = configured.startsWith('http://') || configured.startsWith('https://');
      const base = hasProtocol ? configured : `https://${configured}`;
      return base.replace(/\/$/, '') + '/webdav';
    }
    if (typeof window !== 'undefined') {
      return window.location.origin.replace(/\/$/, '') + '/webdav';
    }
    return '/webdav';
  }, [config.APP_DOMAIN]);

  const handleToggleWebdav = async (checked: boolean) => {
    setWebdavSaving(true);
    try {
      await onSave({ [WEBDAV_KEY]: checked ? '1' : '0' });
      setWebdavEnabled(checked);
    } finally {
      setWebdavSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title={t('WebDAV Mapping')}
        extra={(
          <Space size={12} align="center">
            <Switch
              checked={webdavEnabled}
              loading={webdavSaving}
              disabled={loading}
              onChange={handleToggleWebdav}
            />
          </Space>
        )}
      >
        <Descriptions
          column={1}
          size="small"
          items={[
            {
              key: 'endpoint',
              label: t('WebDAV Endpoint'),
              children: (
                <Typography.Text copyable={{ text: webdavEndpoint }}>
                  <code>{webdavEndpoint}</code>
                </Typography.Text>
              ),
            },
            {
              key: 'auth',
              label: t('Authentication'),
              children: t('Basic (system account password)'),
            },
            {
              key: 'root',
              label: t('Root Path'),
              children: '/webdav',
            },
            {
              key: 'compat',
              label: t('Client Compatibility'),
              children: t('Supports Finder, Windows network drive, rclone, and other WebDAV clients.'),
            },
          ]}
        />
        <Typography.Text type="secondary">
          {t('Toggle the switch to expose the virtual file system via WebDAV.')}
        </Typography.Text>
      </Card>

      <Card title={t('S3 Mapping')}>
        <Typography.Text type="secondary">{t('Coming soon')}</Typography.Text>
      </Card>
    </Space>
  );
}
