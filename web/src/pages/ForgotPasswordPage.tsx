import { useState } from 'react';
import { Card, Form, Input, Button, Typography, message } from 'antd';
import { MailOutlined, ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import { authApi } from '../api/auth';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title, Text } = Typography;

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);

  const handleSubmit = async (values: { email: string }) => {
    setSubmitting(true);
    try {
      await authApi.requestPasswordReset({ email: values.email });
      message.success(t('If the email exists, a reset link has been sent.'));
      setSent(true);
    } catch (err: any) {
      message.error(err?.message || t('Request failed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(to right, var(--ant-color-bg-layout, #f0f2f5), var(--ant-color-fill-secondary, #d7d7d7))',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '48px 16px',
      position: 'relative'
    }}>
      <div style={{ position: 'absolute', top: 16, right: 16 }}>
        <LanguageSwitcher />
      </div>
      <Card
        style={{
          width: '100%',
          maxWidth: 460,
          borderRadius: 20,
          boxShadow: '0 24px 60px rgba(15,23,42,0.12)',
          border: '1px solid rgba(99,102,241,0.12)',
        }}
        styles={{ body: { padding: '40px 36px' } }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 64,
            height: 64,
            borderRadius: '50%',
            margin: '0 auto 16px',
            background: 'linear-gradient(135deg,#6366f1,#8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#fff',
            fontSize: 28,
          }}>
            <MailOutlined />
          </div>
          <Title level={3} style={{ marginBottom: 8 }}>{t('Reset Your Password')}</Title>
          <Text type="secondary">
            {t('Enter the email linked to your account and we will send a reset link.')}
          </Text>
        </div>

        <Form layout="vertical" size="large" onFinish={handleSubmit}>
          <Form.Item
            name="email"
            label={t('Email')}
            rules={[
              { required: true, message: t('Please input recipient email') },
              { type: 'email', message: t('Please input a valid email!') },
            ]}
          >
            <Input placeholder="me@example.com" autoComplete="email" />
          </Form.Item>

          <Form.Item style={{ marginTop: 32 }}>
            <Button type="primary" htmlType="submit" loading={submitting} block>
              {sent ? t('Resend Link') : t('Send Reset Link')}
            </Button>
          </Form.Item>
        </Form>

        <Button
          type="link"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/login')}
          style={{ padding: 0 }}
        >
          {t('Back to login')}
        </Button>
      </Card>
    </div>
  );
}
