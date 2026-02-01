import { useState } from 'react';
import { Card, Form, Input, Button, Typography, Space, Alert } from 'antd';
import { UserOutlined, LockOutlined, MailOutlined } from '@ant-design/icons';
import { useAuth } from '../contexts/AuthContext';
import { useNavigate, Navigate } from 'react-router';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title, Text } = Typography;

export default function RegisterPage() {
  const { isAuthenticated, register, login } = useAuth();
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { t } = useI18n();

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const onFinish = async (values: any) => {
    const username = String(values.username || '').trim();
    const email = String(values.email || '').trim();
    const full_name = String(values.full_name || '').trim();
    const password = String(values.password || '');

    setErr('');
    setLoading(true);
    try {
      await register(username, password, email, full_name || undefined);
      await login(username, password);
      navigate('/', { replace: true });
    } catch (e: any) {
      setErr(e.message || t('Register failed'));
    } finally {
      setLoading(false);
    }
  };

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

      <Card style={{ width: 420 }}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div style={{ textAlign: 'center' }}>
            <Title level={2} style={{ marginBottom: 8 }}>{t('Create Account')}</Title>
            <Text type="secondary">{t('Sign up to your Foxel account')}</Text>
          </div>

          {err && <Alert message={err} type="error" showIcon />}

          <Form layout="vertical" size="large" onFinish={onFinish}>
            <Form.Item
              label={t('Username')}
              name="username"
              rules={[{ required: true, message: t('Please input username!') }]}
            >
              <Input prefix={<UserOutlined />} />
            </Form.Item>

            <Form.Item
              label={t('Email')}
              name="email"
              rules={[
                { required: true, message: t('Please input email!') },
                { type: 'email', message: t('Please input a valid email!') },
              ]}
            >
              <Input prefix={<MailOutlined />} />
            </Form.Item>

            <Form.Item
              label={t('Full Name')}
              name="full_name"
            >
              <Input prefix={<UserOutlined />} />
            </Form.Item>

            <Form.Item
              label={t('Password')}
              name="password"
              rules={[{ required: true, message: t('Please enter password') }]}
            >
              <Input.Password prefix={<LockOutlined />} />
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
              <Input.Password prefix={<LockOutlined />} />
            </Form.Item>

            <Form.Item style={{ marginTop: 8 }}>
              <Button type="primary" htmlType="submit" loading={loading} block>
                {t('Sign Up')}
              </Button>
            </Form.Item>
          </Form>

          <div style={{ textAlign: 'center' }}>
            <Text type="secondary">{t('Already have an account?')}</Text>{' '}
            <Button type="link" style={{ padding: 0 }} onClick={() => navigate('/login')}>
              {t('Sign In')}
            </Button>
          </div>
        </Space>
      </Card>
    </div>
  );
}

