import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Card, Descriptions, Form, Input, Space, Switch, Typography } from 'antd';
import { useI18n } from '../../../i18n';

interface ProtocolMappingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
}

const WEBDAV_KEY = 'WEBDAV_MAPPING_ENABLED';
const S3_KEYS = {
  ENABLED: 'S3_MAPPING_ENABLED',
  BUCKET: 'S3_MAPPING_BUCKET',
  REGION: 'S3_MAPPING_REGION',
  BASE_PATH: 'S3_MAPPING_BASE_PATH',
  ACCESS_KEY: 'S3_MAPPING_ACCESS_KEY',
  SECRET_KEY: 'S3_MAPPING_SECRET_KEY',
};

const truthy = new Set(['1', 'true', 'yes', 'on']);

export default function ProtocolMappingsTab({ config, loading, onSave }: ProtocolMappingsTabProps) {
  const { t } = useI18n();
  const [webdavEnabled, setWebdavEnabled] = useState(() => truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
  const [webdavSaving, setWebdavSaving] = useState(false);
  const [s3Enabled, setS3Enabled] = useState(() => truthy.has((config[S3_KEYS.ENABLED] ?? '1').toLowerCase()));
  const [s3ToggleSaving, setS3ToggleSaving] = useState(false);
  const [s3FormSaving, setS3FormSaving] = useState(false);
  const [s3Form] = Form.useForm();
  const watchBucket = Form.useWatch('bucket', s3Form);
  const watchRegion = Form.useWatch('region', s3Form);
  const watchBasePath = Form.useWatch('basePath', s3Form);
  const watchAccessKey = Form.useWatch('accessKey', s3Form);
  const watchSecretKey = Form.useWatch('secretKey', s3Form);

  useEffect(() => {
    setWebdavEnabled(truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
    setS3Enabled(truthy.has((config[S3_KEYS.ENABLED] ?? '1').toLowerCase()));
    s3Form.setFieldsValue({
      bucket: config[S3_KEYS.BUCKET] ?? 'foxel',
      region: config[S3_KEYS.REGION] ?? 'us-east-1',
      basePath: config[S3_KEYS.BASE_PATH] ?? '/',
      accessKey: config[S3_KEYS.ACCESS_KEY] ?? '',
      secretKey: config[S3_KEYS.SECRET_KEY] ?? '',
    });
  }, [config, s3Form]);

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

  const baseOrigin = useMemo(() => {
    const configured = (config.APP_DOMAIN ?? '').trim();
    if (configured) {
      const hasProtocol = configured.startsWith('http://') || configured.startsWith('https://');
      return (hasProtocol ? configured : `https://${configured}`).replace(/\/$/, '');
    }
    if (typeof window !== 'undefined') {
      return window.location.origin.replace(/\/$/, '');
    }
    return '';
  }, [config.APP_DOMAIN]);

  const bucketValue = (watchBucket ?? config[S3_KEYS.BUCKET] ?? 'foxel').trim() || 'foxel';
  const s3Endpoint = useMemo(() => {
    if (!baseOrigin) return '/s3';
    return `${baseOrigin.replace(/\/$/, '')}/s3`;
  }, [baseOrigin]);
  const bucketApiPath = useMemo(() => `${s3Endpoint.replace(/\/$/, '')}/${encodeURIComponent(bucketValue)}`, [s3Endpoint, bucketValue]);

  const handleToggleS3 = async (checked: boolean) => {
    setS3ToggleSaving(true);
    try {
      await onSave({ [S3_KEYS.ENABLED]: checked ? '1' : '0' });
      setS3Enabled(checked);
    } finally {
      setS3ToggleSaving(false);
    }
  };

  const normalizeBasePath = (value?: string) => {
    const trimmed = (value ?? '/').trim();
    if (!trimmed) return '/';
    if (!trimmed.startsWith('/')) {
      return `/${trimmed}`;
    }
    return trimmed.replace(/\/+$/, '') || '/';
  };

  const regionValue = (watchRegion ?? config[S3_KEYS.REGION] ?? 'us-east-1').trim() || 'us-east-1';
  const basePathValue = normalizeBasePath(watchBasePath ?? config[S3_KEYS.BASE_PATH] ?? '/');
  const accessKeyValue = (watchAccessKey ?? config[S3_KEYS.ACCESS_KEY] ?? '').trim();
  const secretValue = (watchSecretKey ?? config[S3_KEYS.SECRET_KEY] ?? '').trim();
  const exampleCommand = `aws --endpoint-url ${s3Endpoint} s3 ls s3://${bucketValue}/`;

  const handleSaveS3 = async (values: Record<string, string>) => {
    setS3FormSaving(true);
    try {
      await onSave({
        [S3_KEYS.BUCKET]: values.bucket?.trim() || 'foxel',
        [S3_KEYS.REGION]: values.region?.trim() || 'us-east-1',
        [S3_KEYS.BASE_PATH]: normalizeBasePath(values.basePath),
        [S3_KEYS.ACCESS_KEY]: values.accessKey?.trim() || '',
        [S3_KEYS.SECRET_KEY]: values.secretKey?.trim() || '',
      });
    } finally {
      setS3FormSaving(false);
    }
  };

  const hasS3Credentials = Boolean(accessKeyValue && secretValue);

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

      <Card
        title={t('S3 Mapping')}
        extra={(
          <Switch
            checked={s3Enabled}
            loading={s3ToggleSaving}
            disabled={loading}
            onChange={handleToggleS3}
          />
        )}
      >
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {!hasS3Credentials && (
            <Alert
              type="warning"
              message={t('Configure Access Key and Secret to enable S3 mapping.')}
              showIcon
            />
          )}
          <Descriptions
            column={1}
            size="small"
            items={[
              {
                key: 'endpoint',
                label: t('S3 Endpoint'),
                children: (
                  <Typography.Text copyable={{ text: s3Endpoint }}>
                    <code>{s3Endpoint}</code>
                  </Typography.Text>
                ),
              },
              {
                key: 'bucket',
                label: t('Bucket Name'),
                children: bucketValue,
              },
              {
                key: 'bucket-path',
                label: t('Bucket API Path'),
                children: (
                  <Typography.Text copyable={{ text: bucketApiPath }}>
                    <code>{bucketApiPath}</code>
                  </Typography.Text>
                ),
              },
              {
                key: 'region',
                label: t('Region'),
                children: regionValue,
              },
              {
                key: 'base-path',
                label: t('Base Path'),
                children: basePathValue,
              },
              {
                key: 'access',
                label: t('Access Key'),
                children: accessKeyValue ? (
                  <Typography.Text copyable={{ text: accessKeyValue }}>{accessKeyValue}</Typography.Text>
                ) : t('Not set'),
              },
            ]}
          />
          <Form
            form={s3Form}
            layout="vertical"
            onFinish={handleSaveS3}
            disabled={!s3Enabled || loading}
            style={{ width: '100%' }}
          >
            <Form.Item
              name="bucket"
              label={t('Bucket Name')}
              rules={[{ required: true, message: t('Please input bucket name') }]}
            >
              <Input disabled={!s3Enabled || loading} />
            </Form.Item>
            <Form.Item
              name="region"
              label={t('Region')}
              rules={[{ required: true, message: t('Please input region') }]}
            >
              <Input disabled={!s3Enabled || loading} />
            </Form.Item>
            <Form.Item
              name="basePath"
              label={t('Base Path')}
              tooltip={t('Mount point inside the virtual file system (e.g. / or /workspace).')}
            >
              <Input disabled={!s3Enabled || loading} placeholder="/" />
            </Form.Item>
            <Form.Item
              name="accessKey"
              label={t('Access Key')}
              rules={[{ required: true, message: t('Please input access key') }]}
            >
              <Input disabled={!s3Enabled || loading} />
            </Form.Item>
            <Form.Item
              name="secretKey"
              label={t('Secret Key')}
              rules={[{ required: true, message: t('Please input secret key') }]}
            >
              <Input.Password disabled={!s3Enabled || loading} />
            </Form.Item>
            <Form.Item>
              <Button type="primary" htmlType="submit" loading={s3FormSaving} disabled={!s3Enabled} block>
                {t('Save S3 Settings')}
              </Button>
            </Form.Item>
          </Form>
          <Typography.Paragraph type="secondary">
            {t('Example CLI command')}
            <Typography.Text code style={{ display: 'block', marginTop: 8 }} copyable={{ text: exampleCommand }}>
              {exampleCommand}
            </Typography.Text>
          </Typography.Paragraph>
        </Space>
      </Card>
    </Space>
  );
}
