import { useState, useEffect } from 'react';
import { Form, Input, Button, Card, message, Steps, Select, Space, Typography } from 'antd';
import { UserOutlined, LockOutlined, HddOutlined, GlobalOutlined } from '@ant-design/icons';
import { adaptersApi } from '../api/adapters';
import { setConfig } from '../api/config';
import { useAuth } from '../contexts/AuthContext';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title, Text } = Typography;
const { Step } = Steps;

const SetupPage = () => {
  const [loading, setLoading] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [form] = Form.useForm();
  const { login, register } = useAuth();
  const { t } = useI18n();

  // Get current domain for default values
  useEffect(() => {
    const currentDomain = window.location.origin;
    form.setFieldsValue({
      app_domain: currentDomain,
      file_domain: currentDomain
    });
  }, [form]);

  const onFinish = async (values: any) => {
    setLoading(true);
    try {
      await register(values.username, values.password, values.email, values.full_name);
      await login(values.username, values.password);
      message.success(t('Initialization succeeded! Logging you in...'));
      setTimeout(async () => {
        // Save domain configurations
        await setConfig('APP_DOMAIN', values.app_domain);
        await setConfig('FILE_DOMAIN', values.file_domain);
        
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
      }, 2000);
    } catch (error: any) {
      console.log(error)
      message.error(error.response?.data?.msg || t('Initialization failed, please try later'));
    } finally {
      setLoading(false);
    }
  };

  const stepFields = [
    ['db_driver', 'vector_db_driver'],
    ['app_domain', 'file_domain'],
    ['adapter_name', 'adapter_type', 'path', 'root_dir'],
    ['username', 'full_name', 'email', 'password', 'confirm'],
  ]

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
            name="vector_db_driver"
            initialValue="milvus"
            rules={[{ required: true }]}
          >
            <Select size="large" disabled options={[{ label: 'Milvus', value: 'milvus' }]} />
          </Form.Item>
        </>
      )
    },
    {
      title: t('System Configuration'),
      content: (
        <>
          <Title level={4}>{t('Configure system domains')}</Title>
          <Text type="secondary" style={{ marginBottom: 24, display: 'block' }}>{t('Set application and file access domains')}</Text>
          <Form.Item
            label={t('App Domain')}
            name="app_domain"
            rules={[{ required: true, message: t('Please input app domain!') }]}
          >
            <Input size="large" prefix={<GlobalOutlined />} placeholder={t('e.g., https://foxel.example.com')} />
          </Form.Item>
          <Form.Item
            label={t('File Domain')}
            name="file_domain"
            rules={[{ required: true, message: t('Please input file domain!') }]}
          >
            <Input size="large" prefix={<GlobalOutlined />} placeholder={t('e.g., https://foxel.example.com')} />
          </Form.Item>
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
            rules={[{ type: 'email', message: t('Please input a valid email!') }]}
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
      width: '100vw',
      height: '100vh',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(to right, var(--ant-color-bg-layout, #f0f2f5), var(--ant-color-fill-secondary, #d7d7d7))'
    }}>
      <div style={{ position: 'fixed', top: 12, right: 12, zIndex: 1000 }}>
        <LanguageSwitcher />
      </div>
      <Card style={{ width: 'clamp(400px, 40vw, 600px)', padding: '24px 16px' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <img src="/logo.svg" alt="Foxel Logo" style={{ width: 48, marginBottom: 16 }} />
          <Title level={2}>{t('System Initialization')}</Title>
        </div>
        <Steps current={currentStep} style={{ marginBottom: 32 }}>
          {steps.map(item => (
            <Step key={item.title} title={item.title} />
          ))}
        </Steps>

        <Form form={form} name="setup" onFinish={onFinish} layout="vertical">
          {steps.map((step, index) => (
            <div key={step.title} style={{ display: currentStep === index ? 'block' : 'none' }}>
              {step.content}
            </div>
          ))}
        </Form>

        <div style={{ marginTop: 24 }}>
          <Space>
            {currentStep > 0 && (
              <Button style={{ margin: '0 8px' }} onClick={() => prev()}>
                {t('Previous')}
              </Button>
            )}
            {currentStep < steps.length - 1 && (
              <Button type="primary" onClick={() => next()}>
                {t('Next')}
              </Button>
            )}
            {currentStep === steps.length - 1 && (
              <Button type="primary" htmlType="submit" loading={loading} onClick={() => form.submit()}>
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
