import { useEffect, useMemo, useState } from 'react';
import {
  Button,
  Collapse,
  Col,
  Descriptions,
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
import { EyeOutlined, SaveOutlined, SendOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';
import SettingsSection from './SettingsSection';
import {
  sendTestEmail,
  getEmailTemplate,
  updateEmailTemplate,
  previewEmailTemplate,
} from '../../../api/email';

interface EmailSettingsTabProps {
  config: Record<string, string>;
  loading: boolean;
  onSave: (values: Record<string, unknown>) => Promise<boolean>;
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
  } catch {
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
    <div className="fx-email-settings">
      <SettingsSection title={t('SMTP Settings')}>
        <Form<EmailFormValues>
          className="fx-settings-form"
          layout="vertical"
          initialValues={initialValues}
          onFinish={handleSaveConfig}
          key={'email-settings-' + (config?.EMAIL_CONFIG ?? '')}
        >
          <Form.Item name="host" label={t('SMTP Host')} rules={[{ required: true, message: t('Please input SMTP host') }]}>
            <Input size="large" />
          </Form.Item>
          <Form.Item name="port" label={t('SMTP Port')} rules={[{ required: true, message: t('Please input SMTP port') }]}>
            <InputNumber min={1} max={65535} size="large" />
          </Form.Item>
          <Form.Item name="security" label={t('Security')}>
            <Select size="large" options={[
              { value: 'none', label: t('None') },
              { value: 'ssl', label: 'SSL' },
              { value: 'starttls', label: 'STARTTLS' },
            ]} />
          </Form.Item>
          <Form.Item name="timeout" label={t('Timeout (seconds)')}>
            <InputNumber min={1} size="large" />
          </Form.Item>
          <Form.Item name="sender_name" label={t('Sender Name')}>
            <Input size="large" />
          </Form.Item>
          <Form.Item name="sender_email" label={t('Sender Email')} rules={[
            { required: true, message: t('Please input sender email') },
            { type: 'email', message: t('Please input a valid email!') },
          ]}>
            <Input size="large" />
          </Form.Item>
          <Form.Item name="username" label={t('SMTP Username')}>
            <Input size="large" autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label={t('SMTP Password')}>
            <Input.Password size="large" autoComplete="current-password" />
          </Form.Item>
          <Form.Item className="fx-settings-save">
            <Button type="primary" htmlType="submit" loading={loading} icon={<SaveOutlined />}>{t('Save')}</Button>
          </Form.Item>
        </Form>
        <Collapse ghost className="fx-settings-collapse" items={[{
          key: 'current',
          label: t('Current Configuration'),
          children: <Descriptions column={1} className="fx-settings-descriptions" colon={false}
            items={summary.map(item => ({ key: item.label, label: item.label, children: item.value }))} />,
        }]} />
      </SettingsSection>

      <SettingsSection title={t('Test Email')}>
        <Form<TestFormValues>
          form={testForm}
          className="fx-settings-form"
          layout="vertical"
          onFinish={handleTest}
          initialValues={{ subject: t('Foxel Mail Test'), username: '' }}
        >
          <Form.Item name="to" label={t('Recipient Address')} rules={[
            { required: true, message: t('Please input recipient email') },
            { type: 'email', message: t('Please input a valid email!') },
          ]}>
            <Input size="large" />
          </Form.Item>
          <Form.Item name="subject" label={t('Test Subject')}><Input size="large" /></Form.Item>
          <Form.Item name="username" label={t('Test User Name')}>
            <Input size="large" placeholder={t('Optional')} />
          </Form.Item>
          <Form.Item className="fx-settings-save">
            <Button htmlType="submit" loading={testing} icon={<SendOutlined />}>{t('Send Test Email')}</Button>
          </Form.Item>
        </Form>
      </SettingsSection>

      <SettingsSection title={t('Password Reset Template')}>
        <Collapse ghost className="fx-settings-collapse" items={[{
          key: 'template',
          label: t('Edit Template'),
          forceRender: true,
          children: <>
            <Row gutter={[24, 24]}>
              <Col xs={24} lg={12}>
                {templateLoading ? <Skeleton active paragraph={{ rows: 8 }} /> : (
                  <Input.TextArea
                    aria-label={t('Password Reset Template')}
                    value={template}
                    onChange={(e) => { setTemplate(e.target.value); setPreviewHtml(''); }}
                    autoSize={{ minRows: 16, maxRows: 28 }}
                    className="fx-email-template-editor"
                  />
                )}
                <div className="fx-email-template-variables">
                  <Typography.Text type="secondary">{t('Available variables')}</Typography.Text>
                  <Space wrap>
                    <Tag>${'{username}'}</Tag>
                    <Tag>${'{reset_link}'}</Tag>
                    <Tag>${'{expire_minutes}'}</Tag>
                  </Space>
                </div>
              </Col>
              <Col xs={24} lg={12}>
                <h4 className="fx-settings-subheading">{t('Preview Context')}</h4>
                <Form<PreviewContext> layout="vertical" form={previewForm}>
                  <Form.Item name="username" label="username" rules={[{ required: true, message: t('Please complete all required fields') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="reset_link" label="reset_link" rules={[{ required: true, message: t('Please complete all required fields') }]}>
                    <Input />
                  </Form.Item>
                  <Form.Item name="expire_minutes" label="expire_minutes" rules={[{ required: true, message: t('Please complete all required fields') }]}>
                    <InputNumber min={1} style={{ width: '100%' }} />
                  </Form.Item>
                </Form>
                <h4 className="fx-settings-subheading">{t('Live Preview')}</h4>
                <iframe title="email-preview" className="fx-email-template-preview" srcDoc={previewHtml || template} />
              </Col>
            </Row>
            <div className="fx-settings-footer">
              <Space wrap>
                <Button icon={<EyeOutlined />} onClick={handlePreviewTemplate} loading={previewing}>{t('Preview')}</Button>
                <Button type="primary" icon={<SaveOutlined />} onClick={handleSaveTemplate} loading={templateSaving}>{t('Save')}</Button>
              </Space>
            </div>
          </>,
        }]} />
      </SettingsSection>
    </div>
  );
}
