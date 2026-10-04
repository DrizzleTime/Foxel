import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, Descriptions, Form, Input, Space, Switch, Tooltip, Typography } from 'antd';
import { DeleteOutlined, FolderOpenOutlined, PlusOutlined, SaveOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import PathSelectorModal from '../../../components/PathSelectorModal';
import SettingsSection from './SettingsSection';

interface ProtocolMappingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<boolean>;
}

const WEBDAV_KEY = 'WEBDAV_MAPPING_ENABLED';
const S3_KEYS = {
  ENABLED: 'S3_MAPPING_ENABLED',
  BUCKET: 'S3_MAPPING_BUCKET',
  BUCKETS: 'S3_MAPPING_BUCKETS',
  REGION: 'S3_MAPPING_REGION',
  BASE_PATH: 'S3_MAPPING_BASE_PATH',
  ACCESS_KEY: 'S3_MAPPING_ACCESS_KEY',
  SECRET_KEY: 'S3_MAPPING_SECRET_KEY',
};

const truthy = new Set(['1', 'true', 'yes', 'on']);

interface BucketMapping {
  name: string;
  base_path: string;
}

interface S3FormValues {
  buckets: BucketMapping[];
  region: string;
  accessKey: string;
  secretKey: string;
}

function readBucketMappings(config: Record<string, string>): BucketMapping[] {
  const raw = config[S3_KEYS.BUCKETS]?.trim();
  if (raw) {
    const mappings: unknown = JSON.parse(raw);
    if (!Array.isArray(mappings) || !mappings.length || mappings.some(mapping => (
      !mapping || typeof mapping.name !== 'string'
      || (mapping.base_path !== undefined && typeof mapping.base_path !== 'string')
    ))) {
      throw new Error('Invalid bucket mappings');
    }
    return mappings.map(mapping => ({ name: mapping.name, base_path: mapping.base_path ?? '/' }));
  }
  return [{ name: config[S3_KEYS.BUCKET] || 'foxel', base_path: config[S3_KEYS.BASE_PATH] || '/' }];
}

const normalizeBasePath = (value: string) => '/' + value.trim().split('/').filter(Boolean).join('/');
const invalidBasePath = (value: string) => value.includes('\\')
  || Array.from(value).some(char => char.charCodeAt(0) < 32)
  || value.split('/').some(segment => segment === '.' || segment === '..');

export default function ProtocolMappingsTab({ config, loading, onSave }: ProtocolMappingsTabProps) {
  const { t } = useI18n();
  const [webdavEnabled, setWebdavEnabled] = useState(() => truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
  const [webdavSaving, setWebdavSaving] = useState(false);
  const [s3Enabled, setS3Enabled] = useState(() => truthy.has((config[S3_KEYS.ENABLED] ?? '1').toLowerCase()));
  const [s3ToggleSaving, setS3ToggleSaving] = useState(false);
  const [s3FormSaving, setS3FormSaving] = useState(false);
  const [s3Form] = Form.useForm();
  const [bucketConfigError, setBucketConfigError] = useState(false);
  const [pathSelectorIndex, setPathSelectorIndex] = useState<number | null>(null);
  const watchBuckets: BucketMapping[] | undefined = Form.useWatch('buckets', s3Form);
  const watchAccessKey = Form.useWatch('accessKey', s3Form);
  const watchSecretKey = Form.useWatch('secretKey', s3Form);

  useEffect(() => {
    setWebdavEnabled(truthy.has((config[WEBDAV_KEY] ?? '1').toLowerCase()));
    setS3Enabled(truthy.has((config[S3_KEYS.ENABLED] ?? '1').toLowerCase()));
    let buckets: BucketMapping[] = [];
    try {
      buckets = readBucketMappings(config);
      setBucketConfigError(false);
    } catch {
      setBucketConfigError(true);
    }
    s3Form.setFieldsValue({
      buckets,
      region: config[S3_KEYS.REGION] ?? '',
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

  const s3Endpoint = useMemo(() => {
    if (!baseOrigin) return '/s3';
    return `${baseOrigin.replace(/\/$/, '')}/s3`;
  }, [baseOrigin]);

  const handleToggleS3 = async (checked: boolean) => {
    setS3ToggleSaving(true);
    try {
      if (await onSave({ [S3_KEYS.ENABLED]: checked ? '1' : '0' })) {
        setS3Enabled(checked);
      }
    } finally {
      setS3ToggleSaving(false);
    }
  };

  const accessKeyValue = (watchAccessKey ?? config[S3_KEYS.ACCESS_KEY] ?? '').trim();
  const secretValue = (watchSecretKey ?? config[S3_KEYS.SECRET_KEY] ?? '').trim();
  const firstBucketName = watchBuckets?.[0]?.name?.trim();
  const exampleCommand = `aws --endpoint-url ${s3Endpoint} s3 ls${firstBucketName ? ` s3://${firstBucketName}/` : ''}`;
  const handleSaveS3 = async (values: S3FormValues) => {
    setS3FormSaving(true);
    try {
      await onSave({
        [S3_KEYS.BUCKETS]: JSON.stringify(values.buckets.map(bucket => ({
          name: bucket.name.trim(),
          base_path: normalizeBasePath(bucket.base_path),
        }))),
        [S3_KEYS.REGION]: values.region?.trim() || '',
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
      if (await onSave({ [WEBDAV_KEY]: checked ? '1' : '0' })) {
        setWebdavEnabled(checked);
      }
    } finally {
      setWebdavSaving(false);
    }
  };

  return (
    <div className="fx-mapping-settings">
      <SettingsSection
        title={t('WebDAV Mapping')}
        action={(
          <Space size={12} align="center">
            <Switch
              checked={webdavEnabled}
              loading={webdavSaving}
              disabled={loading}
              onChange={handleToggleWebdav}
              aria-label={t('WebDAV Mapping')}
            />
          </Space>
        )}
      >
        <Descriptions
          className="fx-settings-descriptions"
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
      </SettingsSection>

      <SettingsSection
        title={t('S3 Mapping')}
        action={(
          <Switch
            checked={s3Enabled}
            loading={s3ToggleSaving}
            disabled={loading}
            onChange={handleToggleS3}
            aria-label={t('S3 Mapping')}
          />
        )}
      >
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          {bucketConfigError && (
            <Alert type="error" title={t('Invalid S3 bucket configuration')} showIcon />
          )}
          {!hasS3Credentials && (
            <Alert
              type="warning"
              title={t('Configure Access Key and Secret to enable S3 mapping.')}
              showIcon
            />
          )}
          <Descriptions
            className="fx-settings-descriptions"
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
            ]}
          />
          <Form
            form={s3Form}
            layout="vertical"
            onFinish={handleSaveS3}
            disabled={!s3Enabled || loading}
            className="fx-settings-form"
          >
            <Form.List
              name="buckets"
              rules={[{
                validator: async (_, buckets: BucketMapping[] | undefined) => {
                  if (!buckets?.length) throw new Error(t('At least one bucket is required'));
                  const names = buckets.map(bucket => bucket?.name?.trim()).filter(Boolean);
                  if (new Set(names).size !== names.length) throw new Error(t('Bucket names must be unique'));
                },
              }]}
            >
              {(fields, { add, remove }, { errors }) => (
                <div className="fx-s3-buckets">
                  <Typography.Text strong>{t('Bucket Mappings')}</Typography.Text>
                  {fields.map(field => {
                    const bucketName = watchBuckets?.[field.name]?.name?.trim() ?? '';
                    const bucketApiPath = `${s3Endpoint}/${encodeURIComponent(bucketName)}`;
                    return (
                      <div key={field.key} className="fx-s3-bucket">
                        <div className="fx-s3-bucket-heading">
                          <Typography.Text type="secondary">{t('Bucket Name')}</Typography.Text>
                          <Tooltip title={t('Remove')}>
                            <Button
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              aria-label={t('Remove')}
                              disabled={fields.length <= 1 || !s3Enabled || loading}
                              onClick={() => remove(field.name)}
                            />
                          </Tooltip>
                        </div>
                        <Form.Item
                          name={[field.name, 'name']}
                          rules={[
                            { required: true, whitespace: true, message: t('Please input bucket name') },
                            {
                              validator: async (_, value: string) => {
                                if (value?.trim() && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$/.test(value.trim())) {
                                  throw new Error(t('Invalid bucket name'));
                                }
                              },
                            },
                          ]}
                        >
                          <Input aria-label={t('Bucket Name')} />
                        </Form.Item>
                        <Form.Item
                          name={[field.name, 'base_path']}
                          label={t('Base Path')}
                          tooltip={t('Mount point inside the virtual file system (e.g. / or /workspace).')}
                          rules={[
                            { required: true, whitespace: true, message: t('Please input base path') },
                            {
                              validator: async (_, value: string) => {
                                if (value && invalidBasePath(value.trim())) throw new Error(t('Invalid base path'));
                              },
                            },
                          ]}
                        >
                          <Input
                            placeholder="/"
                            addonAfter={(
                              <Tooltip title={t('Select Folder')}>
                                <Button
                                  type="text"
                                  size="small"
                                  icon={<FolderOpenOutlined />}
                                  aria-label={t('Select Folder')}
                                  disabled={!s3Enabled || loading}
                                  onClick={() => setPathSelectorIndex(field.name)}
                                />
                              </Tooltip>
                            )}
                          />
                        </Form.Item>
                        {bucketName && (
                          <div className="fx-s3-bucket-endpoint">
                            <Typography.Text type="secondary">{t('Bucket API Path')}</Typography.Text>
                            <Typography.Text copyable={{ text: bucketApiPath }}><code>{bucketApiPath}</code></Typography.Text>
                          </div>
                        )}
                      </div>
                    );
                  })}
                  <Form.ErrorList errors={errors} />
                  <Button icon={<PlusOutlined />} disabled={!s3Enabled || loading} onClick={() => add({ name: '', base_path: '/' })}>
                    {t('Add Bucket')}
                  </Button>
                </div>
              )}
            </Form.List>
            <Form.Item
              name="region"
              label={t('Region')}
              extra={t('Leave blank to accept any region.')}
            >
              <Input disabled={!s3Enabled || loading} placeholder="us-east-1" />
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
            <Form.Item className="fx-settings-save">
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={s3FormSaving} disabled={!s3Enabled}>
                {t('Save S3 Settings')}
              </Button>
            </Form.Item>
          </Form>
          <Typography.Paragraph type="secondary">
            {t('Example CLI command')}
            <Typography.Text className="fx-settings-command" copyable={{ text: exampleCommand }}>
              {exampleCommand}
            </Typography.Text>
          </Typography.Paragraph>
        </Space>
      </SettingsSection>
      <PathSelectorModal
        open={pathSelectorIndex !== null}
        initialPath={pathSelectorIndex === null ? '/' : s3Form.getFieldValue(['buckets', pathSelectorIndex, 'base_path']) || '/'}
        onCancel={() => setPathSelectorIndex(null)}
        onOk={path => {
          if (pathSelectorIndex !== null) s3Form.setFieldValue(['buckets', pathSelectorIndex, 'base_path'], path);
          setPathSelectorIndex(null);
        }}
      />
    </div>
  );
}
