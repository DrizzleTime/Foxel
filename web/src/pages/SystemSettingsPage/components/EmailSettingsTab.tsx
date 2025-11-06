import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Typography,
  message,
  Tag,
  Skeleton,
} from 'antd';
import { HighlightOutlined, EyeOutlined, SaveOutlined, SendOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import {
  sendTestEmail,
  getEmailTemplate,
  updateEmailTemplate,
  previewEmailTemplate,
} from '../../../api/email';

interface EmailSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<void>;
}

interface EmailFormValues {
  host: string;
  port: number;
  username?: string;
  password?: string;
  sender_name?: string;
  sender_email: string;
  security: 'none' | 'ssl' | 'starttls';
  timeout?: number;
}

interface TestFormValues {
  to: string;
  subject: string;
  username?: string;
}

interface PreviewContext extends Record<string, unknown> {
  username: string;
  reset_link: string;
  expire_minutes: number;
}

const DEFAULT_FORM: EmailFormValues = {
  host: '',
  port: 465,
  username: '',
  password: '',
  sender_name: '',
  sender_email: '',
  security: 'ssl',
  timeout: 30,
};

const TEMPLATE_NAME = 'password_reset';

function parseEmailConfig(raw?: string | null): EmailFormValues {
  if (!raw) return { ...DEFAULT_FORM };
  try {
    const data = JSON.parse(raw) as Partial<EmailFormValues>;
    return {
      ...DEFAULT_FORM,
      ...data,
      port: Number(data?.port ?? DEFAULT_FORM.port),
      timeout: data?.timeout !== undefined ? Number(data.timeout) : DEFAULT_FORM.timeout,
      security: (data?.security ?? DEFAULT_FORM.security) as EmailFormValues['security'],
    };
  } catch (_err) {
    return { ...DEFAULT_FORM };
  }
}

export default function EmailSettingsTab({ config, loading, onSave }: EmailSettingsTabProps) {
  const { t } = useI18n();
  const [testForm] = Form.useForm<TestFormValues>();
  const [previewForm] = Form.useForm<PreviewContext>();
  const [testing, setTesting] = useState(false);
  const [template, setTemplate] = useState<string>('');
  const [templateLoading, setTemplateLoading] = useState(true);
  const [templateSaving, setTemplateSaving] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string>('');

  const initialValues = useMemo(() => parseEmailConfig(config?.EMAIL_CONFIG), [config]);

  const summary = useMemo(() => {
    const parsed = parseEmailConfig(config?.EMAIL_CONFIG);
    return [
      { label: t('SMTP Host'), value: parsed.host || '-' },
      { label: t('SMTP Port'), value: parsed.port || '-' },
      { label: t('Security'), value: parsed.security.toUpperCase() },
      { label: t('Sender Email'), value: parsed.sender_email || '-' },
      { label: t('Sender Name'), value: parsed.sender_name || t('Not set') },
      { label: t('Timeout (seconds)'), value: parsed.timeout || '-' },
    ];
  }, [config, t]);

  useEffect(() => {
    setTemplateLoading(true);
    getEmailTemplate(TEMPLATE_NAME)
      .then((res) => setTemplate(res.content))
      .catch((err) => {
        message.error(err?.message || t('Failed to load template'));
      })
      .finally(() => setTemplateLoading(false));
  }, [t]);

  useEffect(() => {
    previewForm.setFieldsValue({
      username: 'Foxel 用户',
      reset_link: 'https://foxel.cc/reset-password?token=demo',
      expire_minutes: 10,
    });
  }, [previewForm]);

  const handleSaveConfig = async (values: EmailFormValues) => {
    if (!values.host || !values.port || !values.sender_email) {
      message.error(t('Please complete all required fields'));
      return;
    }
    const payload: Record<string, unknown> = {
      host: values.host.trim(),
      port: Number(values.port),
      sender_email: values.sender_email.trim(),
      security: values.security,
    };
    if (!Number.isFinite(payload.port as number) || (payload.port as number) <= 0) {
      message.error(t('SMTP port must be a positive number'));
      return;
    }
    if (values.username?.trim()) {
      payload.username = values.username.trim();
    }
    if (values.password?.length) {
      payload.password = values.password;
    }
    if (values.sender_name?.trim()) {
      payload.sender_name = values.sender_name.trim();
    }
    if (values.timeout !== undefined && values.timeout !== null) {
      const timeoutNumber = Number(values.timeout);
      if (Number.isFinite(timeoutNumber) && timeoutNumber > 0) {
        payload.timeout = timeoutNumber;
      }
    }
    await onSave({ EMAIL_CONFIG: JSON.stringify(payload) });
  };

  const handleTest = async () => {
    try {
      const values = await testForm.validateFields();
      setTesting(true);
      const response = await sendTestEmail({
        to: values.to,
        subject: values.subject,
        template: 'test',
        context: { username: values.username || values.to },
      });
      message.success(t('Test email queued (task {{taskId}})', { taskId: response.task_id }));
    } catch (err: any) {
      if (err?.errorFields) {
        return;
      }
      message.error(err?.message || t('Test email failed'));
    } finally {
      setTesting(false);
    }
  };

  const handlePreviewTemplate = async () => {
    try {
      const values = await previewForm.validateFields();
      setPreviewing(true);
      const res = await previewEmailTemplate(TEMPLATE_NAME, values);
      setPreviewHtml(res.html);
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error(err?.message || t('Preview failed'));
    } finally {
      setPreviewing(false);
    }
  };

  const handleSaveTemplate = async () => {
    setTemplateSaving(true);
    try {
      await updateEmailTemplate(TEMPLATE_NAME, template);
      message.success(t('Template saved'));
    } catch (err: any) {
      message.error(err?.message || t('Failed to save template'));
    } finally {
      setTemplateSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={32} style={{ width: '100%', marginTop: 24 }}>
      <Row gutter={24}>
        <Col xs={24} lg={15}>
          <Card
            title={t('SMTP Settings')}
            extra={<InfoCircleOutlined style={{ color: 'var(--ant-color-primary)' }} />}
            bodyStyle={{ paddingBottom: 12 }}
          >
            <Form<EmailFormValues>
              layout="vertical"
              initialValues={initialValues}
              onFinish={handleSaveConfig}
              key={'email-settings-' + (config?.EMAIL_CONFIG ?? '')}
            >
              <Row gutter={16}>
                <Col span={14}>
                  <Form.Item
                    name="host"
                    label={t('SMTP Host')}
                    rules={[{ required: true, message: t('Please input SMTP host') }]}
                  >
                    <Input size="large" />
                  </Form.Item>
                </Col>
                <Col span={10}>
                  <Form.Item
                    name="port"
                    label={t('SMTP Port')}
                    rules={[{ required: true, message: t('Please input SMTP port') }]}
                  >
                    <InputNumber min={1} style={{ width: '100%' }} size="large" />
                  </Form.Item>
                </Col>
              </Row>
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="security" label={t('Security')}>
                    <Select
                      size="large"
                      options={[
                        { value: 'none', label: t('None') },
                        { value: 'ssl', label: 'SSL' },
                        { value: 'starttls', label: 'STARTTLS' },
                      ]}
                    />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="timeout" label={t('Timeout (seconds)')}>
                    <InputNumber min={1} style={{ width: '100%' }} size="large" />
                  </Form.Item>
                </Col>
              </Row>
              <Divider />
              <Form.Item name="sender_name" label={t('Sender Name')}>
                <Input size="large" />
              </Form.Item>
              <Form.Item
                name="sender_email"
                label={t('Sender Email')}
                rules={[
                  { required: true, message: t('Please input sender email') },
                  { type: 'email', message: t('Please input a valid email!') },
                ]}
              >
                <Input size="large" />
              </Form.Item>
              <Divider />
              <Row gutter={16}>
                <Col span={12}>
                  <Form.Item name="username" label={t('SMTP Username')}>
                    <Input size="large" autoComplete="username" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="password" label={t('SMTP Password')}>
                    <Input.Password size="large" autoComplete="current-password" />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item style={{ marginTop: 24 }}>
                <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />} block>
                  {t('Save')}
                </Button>
              </Form.Item>
            </Form>
          </Card>
        </Col>
        <Col xs={24} lg={9}>
          <Space direction="vertical" size={24} style={{ width: '100%' }}>
            <Card title={t('Current Configuration')} bodyStyle={{ paddingBottom: 12 }}>
              <Descriptions column={1} size="small" colon={false}>
                {summary.map(item => (
                  <Descriptions.Item key={item.label} label={<TextLabel text={item.label} />}>
                    <Typography.Text strong>{item.value}</Typography.Text>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </Card>
            <Card title={t('Test Email')} extra={<SendOutlined style={{ color: 'var(--ant-color-primary)' }} />}>
              <Form<TestFormValues>
                form={testForm}
                layout="vertical"
                initialValues={{
                  subject: t('Foxel Mail Test'),
                  username: '',
                }}
              >
                <Form.Item
                  name="to"
                  label={t('Recipient Address')}
                  rules={[
                    { required: true, message: t('Please input recipient email') },
                    { type: 'email', message: t('Please input a valid email!') },
                  ]}
                >
                  <Input size="large" />
                </Form.Item>
                <Form.Item name="subject" label={t('Test Subject')}>
                  <Input size="large" />
                </Form.Item>
                <Form.Item name="username" label={t('Test User Name')}>
                  <Input size="large" placeholder={t('Optional')} />
                </Form.Item>
                <Button type="primary" onClick={handleTest} loading={testing} block icon={<SendOutlined />}>
                  {t('Send Test Email')}
                </Button>
              </Form>
            </Card>
          </Space>
        </Col>
      </Row>

      <Card
        title={
          <Space>
            <HighlightOutlined />
            {t('Password Reset Template')}
          </Space>
        }
        extra={
          <Space>
            <Button icon={<EyeOutlined />} onClick={handlePreviewTemplate} loading={previewing}>
              {t('Preview')}
            </Button>
            <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTemplate} loading={templateSaving}>
              {t('Save')}
            </Button>
          </Space>
        }
      >
        <Row gutter={24}>
          <Col xs={24} lg={14}>
            {templateLoading ? (
              <Skeleton active paragraph={{ rows: 8 }} />
            ) : (
              <Input.TextArea
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
                autoSize={{ minRows: 20 }}
                style={{ fontFamily: 'monospace', background: '#0f172a', color: '#e2e8f0' }}
              />
            )}
            <div style={{ marginTop: 16 }}>
              <Typography.Text type="secondary">{t('Available variables')}：</Typography.Text>
              <Space wrap style={{ marginTop: 8 }}>
                <Tag color="blue">${'{username}'}</Tag>
                <Tag color="blue">${'{reset_link}'}</Tag>
                <Tag color="blue">${'{expire_minutes}'}</Tag>
              </Space>
            </div>
          </Col>
          <Col xs={24} lg={10}>
            <Card title={t('Preview Context')} size="small" style={{ marginBottom: 16 }}>
              <Form<PreviewContext> layout="vertical" form={previewForm}>
                <Form.Item
                  name="username"
                  label="username"
                  rules={[{ required: true, message: t('Please complete all required fields') }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="reset_link"
                  label="reset_link"
                  rules={[{ required: true, message: t('Please complete all required fields') }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="expire_minutes"
                  label="expire_minutes"
                  rules={[{ required: true, message: t('Please complete all required fields') }]}
                >
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </Form>
            </Card>
            <Card title={t('Live Preview')} size="small" className="email-template-preview">
              <div
                style={{
                  border: '1px solid rgba(148,163,184,0.2)',
                  borderRadius: 12,
                  overflow: 'hidden',
                  height: 360,
                  background: '#f8fafc',
                  padding: 0,
                }}
              >
                <iframe
                  title="email-preview"
                  style={{
                    width: '100%',
                    height: '100%',
                    border: 'none',
                    backgroundColor: '#f8fafc',
                  }}
                  srcDoc={previewHtml || template}
                />
              </div>
            </Card>
          </Col>
        </Row>
      </Card>
    </Space>
  );
}

function TextLabel({ text }: { text: string }) {
  return <Typography.Text type="secondary">{text}</Typography.Text>;
}
