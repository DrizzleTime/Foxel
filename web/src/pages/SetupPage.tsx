import { useEffect, useState } from 'react';
import { Form, Input, Button, Card, message, Steps, Select, Space, Typography, Alert, Grid } from 'antd';
import { UserOutlined, LockOutlined, HddOutlined } from '@ant-design/icons';
import { adaptersApi } from '../api/adapters';
import { setConfig } from '../api/config';
import { vectorDBApi, type VectorDBProviderMeta } from '../api/vectorDB';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title, Text } = Typography;

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

const SetupPage = () => {
  const screens = Grid.useBreakpoint();
  const isMobile = !screens.md;
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();
  const { login, register } = useAuth();
  const { t } = useI18n();
  const [vectorProviders, setVectorProviders] = useState<VectorDBProviderMeta[]>([]);
  const [vectorProvidersLoading, setVectorProvidersLoading] = useState(false);
  const [selectedVectorProviderType, setSelectedVectorProviderType] = useState<string | null>(null);

  useEffect(() => {
    const origin = window.location.origin;
    form.setFieldsValue({
      app_domain: origin,
      file_domain: origin,
    });
  }, [form]);

  useEffect(() => {
    let mounted = true;
    async function loadVectorProviders() {
      setVectorProvidersLoading(true);
      try {
        const providers = await vectorDBApi.getProviders();
        if (!mounted) return;
        setVectorProviders(providers);

        const enabled = providers.filter((item) => item.enabled);
        const currentType = form.getFieldValue('vector_db_type') as string | undefined;
        let nextType = currentType;
        if (!nextType || !providers.some((item) => item.type === nextType && item.enabled)) {
          nextType = enabled.find((item) => item.type === 'milvus_lite')?.type
            ?? enabled[0]?.type
            ?? providers[0]?.type
            ?? 'milvus_lite';
        }

        setSelectedVectorProviderType(nextType);
        const provider = providers.find((item) => item.type === nextType);
        const existingConfig = nextType === currentType ? (form.getFieldValue('vector_db_config') as Record<string, string> | undefined) : undefined;
        const configValues = buildProviderConfigValues(provider, existingConfig);
        form.setFieldsValue({ vector_db_type: nextType, vector_db_config: configValues });
      } catch (e: any) {
        console.error(e);
        message.error(e?.message || t('Load failed'));
        if (mounted) {
          form.setFieldsValue({ vector_db_type: 'milvus_lite' });
          setSelectedVectorProviderType('milvus_lite');
        }
      } finally {
        if (mounted) setVectorProvidersLoading(false);
      }
    }
    loadVectorProviders();
    return () => {
      mounted = false;
    };
  }, [form, t]);

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      await register(values.username, values.password, values.email, values.full_name);
      await login(values.username, values.password);
        message.success(t('Initialization succeeded! Logging you in...'));
      setTimeout(async () => {
        try {
          const tasks: Promise<unknown>[] = [];
          const appDomain = values.app_domain?.trim();
          const fileDomain = values.file_domain?.trim();
          if (appDomain) {
            tasks.push(setConfig('APP_DOMAIN', appDomain));
          }
          if (fileDomain) {
            tasks.push(setConfig('FILE_DOMAIN', fileDomain));
          }
          if (tasks.length) {
            await Promise.all(tasks);
          }
          if (values.vector_db_type) {
            const configPayload = Object.fromEntries(
              Object.entries(values.vector_db_config || {})
                .filter(([, val]) => val !== undefined && val !== null && String(val).trim() !== '')
                .map(([key, val]) => [key, String(val)]),
            );
            try {
              await vectorDBApi.updateConfig({ type: values.vector_db_type, config: configPayload });
            } catch (e: any) {
              console.error(e);
              message.warning(e?.message || t('Vector DB setup failed, you can configure it later in System Settings'));
            }
          }
          await adaptersApi.create({
            name: values.adapter_name,
            type: values.adapter_type,
            config: {
              root: values.root_dir
            },
            sub_path: null,
            path: values.path,
            enabled: true
          });
          window.location.href = '/';
        } catch (configError: any) {
          console.error(configError);
          message.error(configError.response?.data?.msg || t('Initialization failed, please try later'));
        }
      }, 2000);
    } catch (error: any) {
      console.log(error)
      message.error(error.response?.data?.msg || t('Initialization failed, please try later'));
    } finally {
      setLoading(false);
    }
  };

  const selectedVectorProvider = vectorProviders.find((item) => item.type === selectedVectorProviderType) || vectorProviders.find((item) => item.enabled) || vectorProviders[0];
  const requiredVectorConfigFields = (selectedVectorProvider?.config_schema || [])
    .filter((field) => field.required)
    .map((field) => ['vector_db_config', field.key]);

  const stepFields: any[] = [
    ['db_driver', 'vector_db_type', ...requiredVectorConfigFields],
    ['adapter_name', 'adapter_type', 'path', 'root_dir'],
    ['username', 'full_name', 'email', 'password', 'confirm'],
  ]

  const handleVectorProviderChange = (value: string) => {
    setSelectedVectorProviderType(value);
    const provider = vectorProviders.find((item) => item.type === value);
    const configValues = buildProviderConfigValues(provider);
    form.setFieldsValue({ vector_db_type: value, vector_db_config: configValues });
  };

  const next = () => {
    form.validateFields(stepFields[currentStep]).then(() => {
      setCurrentStep(currentStep + 1);
    })
  };

  const prev = () => {
    setCurrentStep(currentStep - 1);
  };

  const steps = [
    {
      title: t('Database Setup'),
      content: (
        <>
          <Title level={4}>{t('Choose database driver')}</Title>
          <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>{t('Select database and vector database for system data')}</Text>
          <Form.Item
            label={t('Database Driver')}
            name="db_driver"
            initialValue="sqlite"
            rules={[{ required: true }]}
          >
            <Select size="large" prefix={<HddOutlined />} disabled options={[{ label: 'SQLite', value: 'sqlite' }]} />
          </Form.Item>
          <Form.Item
            label={t('Vector DB Driver')}
            name="vector_db_type"
            initialValue="milvus_lite"
            rules={[{ required: true }]}
          >
            <Select
              size="large"
              loading={vectorProvidersLoading}
              disabled={vectorProvidersLoading || !vectorProviders.length}
              options={vectorProviders.map((provider) => ({
                value: provider.type,
                label: provider.label,
                disabled: !provider.enabled,
              }))}
              onChange={handleVectorProviderChange}
            />
          </Form.Item>
          {selectedVectorProvider?.description ? (
            <Alert
              type="info"
              showIcon
              message={t(selectedVectorProvider.description)}
              style={{ marginBottom: 16 }}
            />
          ) : null}
          {selectedVectorProvider?.config_schema?.map((field) => (
            <Form.Item
              key={field.key}
              name={['vector_db_config', field.key]}
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
        </>
      )
    },
    {
      title: t('Initialize Mount'),
      content: (
        <>
          <Title level={4}>{t('Configure initial storage')}</Title>
          <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>{t('Create the first storage mount for your files')}</Text>
          <Form.Item
            label={t('Mount Name')}
            name="adapter_name"
            initialValue={t('Local Storage')}
            rules={[{ required: true, message: t('Please input mount name!') }]}
          >
            <Input size="large" prefix={<HddOutlined />} />
          </Form.Item>
          <Form.Item
            label={t('Storage Type')}
            name="adapter_type"
            initialValue="local"
            rules={[{ required: true }]}
          >
            <Select size="large" disabled options={[{ label: t('Local Storage'), value: 'local' }]} />
          </Form.Item>
          <Form.Item
            label={t('Mount Path')}
            name="path"
            initialValue="/local"
            rules={[{ required: true, message: t('Please input mount path!') }]}
          >
            <Input size="large" prefix={<HddOutlined />} />
          </Form.Item>
          <Form.Item
            label={t('Root Directory')}
            name="root_dir"
            initialValue="data/mount"
            rules={[{ required: true, message: t('Please input root directory!') }]}
          >
            <Input size="large" placeholder={t('e.g., data/ or /var/foxel/data')} />
          </Form.Item>
          <Form.Item
            label={t('App Domain')}
            name="app_domain"
            extra={t('Optional, used for external links. Leave empty to use the current site.')}
          >
            <Input size="large" placeholder="https://your-app-domain.com" />
          </Form.Item>
          <Form.Item
            label={t('File Domain')}
            name="file_domain"
            extra={t('Optional, used for external links. Leave empty to use the current site.')}
          >
            <Input size="large" placeholder="https://files.your-domain.com" />
          </Form.Item>
        </>
      )
    },
    {
      title: t('Create Admin'),
      content: (
        <>
          <Title level={4}>{t('Create admin account')}</Title>
          <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>{t('This is the first account with full permissions')}</Text>
          <Form.Item
            label={t('Username')}
            name="username"
            rules={[{ required: true, message: t('Please input username!') }]}
          >
            <Input size="large" prefix={<UserOutlined />} />
          </Form.Item>

          <Form.Item
            label={t('Full Name')}
            name="full_name"
          >
            <Input size="large" prefix={<UserOutlined />} />
          </Form.Item>

          <Form.Item
            label={t('Email')}
            name="email"
            rules={[
              { required: true, message: t('Please input email!') },
              { type: 'email', message: t('Please input a valid email!') },
            ]}
          >
            <Input size="large" prefix={<UserOutlined />} />
          </Form.Item>

          <Form.Item
            label={t('Password')}
            name="password"
            rules={[{ required: true, message: t('Please enter password') }]}
          >
            <Input.Password size="large" prefix={<LockOutlined />} />
          </Form.Item>

          <Form.Item
            label={t('Confirm Password')}
            name="confirm"
            dependencies={['password']}
            hasFeedback
            rules={[
              { required: true, message: t('Please confirm your password!') },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('password') === value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error(t('Passwords do not match!')));
                },
              }),
            ]}
          >
            <Input.Password size="large" prefix={<LockOutlined />} />
          </Form.Item>
        </>
      )
    },
  ];

  return (
    <div style={{
      display: 'flex',
      width: '100%',
      minHeight: '100vh',
      alignItems: isMobile ? 'flex-start' : 'center',
      justifyContent: 'center',
      padding: isMobile ? '64px 12px 24px' : '32px 24px',
      boxSizing: 'border-box',
      background: 'linear-gradient(to right, var(--ant-color-bg-layout, #f0f2f5), var(--ant-color-fill-secondary, #d7d7d7))'
    }}>
      <div style={{ position: 'fixed', top: 12, right: 12, zIndex: 1000 }}>
        <LanguageSwitcher />
      </div>
      <Card
        style={{ width: '100%', maxWidth: 800 }}
        styles={{ body: { padding: isMobile ? '18px 14px' : '24px 20px' } }}
      >
        <div style={{ textAlign: 'center', marginBottom: isMobile ? 20 : 32 }}>
          <img src="/logo.svg" alt="Foxel Logo" style={{ width: 48, marginBottom: 16 }} />
          <Title level={2}>{t('System Initialization')}</Title>
        </div>
        <Steps
          current={currentStep}
          direction={isMobile ? 'vertical' : 'horizontal'}
          size={isMobile ? 'small' : 'default'}
          style={{ marginBottom: isMobile ? 20 : 32 }}
          items={steps.map((item) => ({ title: item.title }))}
        />

        <Form form={form} name="setup" onFinish={onFinish} layout="vertical">
          {steps.map((step, index) => (
            <div key={step.title} style={{ display: currentStep === index ? 'block' : 'none' }}>
              {step.content}
            </div>
          ))}
        </Form>

        <div style={{ marginTop: isMobile ? 16 : 24 }}>
          <Space direction={isMobile ? 'vertical' : 'horizontal'} style={{ width: '100%' }}>
            {currentStep > 0 && (
              <Button block={isMobile} onClick={() => prev()}>
                {t('Previous')}
              </Button>
            )}
            {currentStep < steps.length - 1 && (
              <Button type="primary" block={isMobile} onClick={() => next()}>
                {t('Next')}
              </Button>
            )}
            {currentStep === steps.length - 1 && (
              <Button type="primary" block={isMobile} htmlType="submit" loading={loading} onClick={() => form.submit()}>
                {t('Finish Initialization')}
              </Button>
            )}
          </Space>
        </div>
      </Card>
    </div>
  );
};

export default SetupPage;
