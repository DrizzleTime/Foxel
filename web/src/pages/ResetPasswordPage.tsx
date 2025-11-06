import { useEffect, useMemo, useState } from 'react';
import { Card, Form, Input, Button, Typography, message, Result } from 'antd';
import { LockOutlined, CheckCircleTwoTone } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router';
import { authApi } from '../api/auth';
import { useI18n } from '../i18n';
import LanguageSwitcher from '../components/LanguageSwitcher';

const { Title, Text } = Typography;

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const token = useMemo(() => new URLSearchParams(location.search).get('token') || '', [location.search]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [userInfo, setUserInfo] = useState<{ username: string; email: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) {
      setError(t('Reset link is invalid'));
      setLoading(false);
      return;
    }
    authApi.verifyPasswordResetToken(token)
      .then(setUserInfo)
      .catch((err) => {
        setError(err?.message || t('Reset link is invalid or expired'));
      })
      .finally(() => setLoading(false));
  }, [token, t]);

  const handleSubmit = async (values: { password: string; confirm: string }) => {
    if (values.password !== values.confirm) {
      message.error(t('Passwords do not match'));
      return;
    }
    setSubmitting(true);
    try {
      await authApi.confirmPasswordReset({ token, password: values.password });
      setSuccess(true);
      message.success(t('Password updated, please login again.'));
      setTimeout(() => navigate('/login'), 1500);
    } catch (err: any) {
      message.error(err?.message || t('Failed to reset password'));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return null;
  }

  if (error) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Result
          status="error"
          title={t('Reset failed')}
          subTitle={error}
          extra={[
            <Button type="primary" key="back" onClick={() => navigate('/forgot-password')}>
              {t('Try again')}
            </Button>,
          ]}
        />
      </div>
    );
  }

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
          maxWidth: 480,
          borderRadius: 20,
          border: '1px solid rgba(99,102,241,0.14)',
          boxShadow: '0 24px 60px rgba(79,70,229,0.18)',
        }}
        bodyStyle={{ padding: '40px 36px' }}
      >
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            width: 64,
            height: 64,
            borderRadius: '50%',
            margin: '0 auto 16px',
            background: success ? '#ecfdf5' : 'linear-gradient(135deg,#6366f1,#8b5cf6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: success ? '#047857' : '#fff',
            fontSize: success ? 32 : 28,
          }}>
            {success ? <CheckCircleTwoTone twoToneColor="#22c55e" /> : <LockOutlined />}
          </div>
          <Title level={3} style={{ marginBottom: 8 }}>{t('Set a new password')}</Title>
          {userInfo && <Text type="secondary">{userInfo.email}</Text>}
        </div>

        <Form layout="vertical" size="large" onFinish={handleSubmit}>
          <Form.Item
            name="password"
            label={t('New Password')}
            rules={[{ required: true, message: t('Please enter new password') }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item
            name="confirm"
            label={t('Confirm Password')}
            rules={[{ required: true, message: t('Please confirm new password') }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Button
            type="primary"
            htmlType="submit"
            loading={submitting}
            block
            size="large"
          >
            {t('Update Password')}
          </Button>
        </Form>
      </Card>
    </div>
  );
}
