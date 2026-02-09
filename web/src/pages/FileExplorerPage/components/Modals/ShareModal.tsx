import { memo, useState, useEffect } from 'react';
import { Modal, Form, Input, Radio, InputNumber, message, Button, Typography } from 'antd';
import { CopyOutlined } from '@ant-design/icons';
import type { VfsEntry, ShareInfoWithPassword } from '../../../../api/client';
import { shareApi } from '../../../../api/share';
import { useSystemStatus } from '../../../../contexts/SystemContext';
import { useI18n } from '../../../../i18n';

interface ShareModalProps {
  entries: VfsEntry[];
  path: string;
  open: boolean;
  onOk: () => void;
  onCancel: () => void;
}

export const ShareModal = memo(function ShareModal({ entries, path, open, onOk, onCancel }: ShareModalProps) {
  const systemStatus = useSystemStatus();
  const { t } = useI18n();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [accessType, setAccessType] = useState('public');
  const [createdShare, setCreatedShare] = useState<ShareInfoWithPassword | null>(null);

  const defaultName = entries.length > 1
    ? t('Share {count} items', { count: entries.length.toString() })
    : (entries.length === 1 ? entries[0].name : '');

  useEffect(() => {
    if (open) {
      setCreatedShare(null);
      form.setFieldsValue({
        name: defaultName,
        accessType: 'public',
        expiresInDays: 7,
        password: '',
      });
      setAccessType('public');
    }
  }, [open, defaultName, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      const fullPaths = entries.map(e => {
        const p = path === '/' ? '' : path;
        return `${p}/${e.name}`;
      });

      const result = await shareApi.create({
        name: values.name,
        paths: fullPaths,
        access_type: values.accessType,
        password: values.password,
        expires_in_days: values.expiresInDays,
      });
      message.success(t('Share link created'));
      setCreatedShare(result);
    } catch (e: any) {
      message.error(e.message || t('Create failed'));
    } finally {
      setLoading(false);
    }
  };
  
  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    message.success(t('Copied to clipboard'));
  };

  const baseUrl = systemStatus?.app_domain || window.location.origin;
  const shareUrl = createdShare ? new URL(`/share/${createdShare.token}`, baseUrl).href : '';

  const renderForm = () => (
    <Form form={form} layout="vertical" initialValues={{ name: defaultName, accessType: 'public', expiresInDays: 7 }}>
      <Form.Item name="name" label={t('Share Name')} rules={[{ required: true }]} >
        <Input />
      </Form.Item>
      <Form.Item name="accessType" label={t('Access')}>
        <Radio.Group onChange={(e) => setAccessType(e.target.value)}>
          <Radio value="public">{t('Public')}</Radio>
          <Radio value="password">{t('By Password')}</Radio>
        </Radio.Group>
      </Form.Item>
      {accessType === 'password' && (
        <Form.Item name="password" label={t('Please enter password')} rules={[{ required: true, message: t('Please enter password') }]} >
          <Input.Password />
        </Form.Item>
      )}
      <Form.Item name="expiresInDays" label={t('Expiration (days)')} help={t('Set 0 or negative for forever')}>
        <InputNumber min={-1} style={{ width: '100%' }} />
      </Form.Item>
    </Form>
  );

  const renderSuccess = () => (
    <div>
      <Typography.Paragraph>{t('Share link created successfully!')}</Typography.Paragraph>
      <Form layout="vertical">
        <Form.Item label={t('Share Link')}>
          <div style={{ display: 'flex', gap: 8 }}>
        <Input readOnly value={shareUrl} style={{ flex: 1 }} />
        <Button icon={<CopyOutlined />} onClick={() => handleCopy(shareUrl)}>
          {t('Copy')}
        </Button>
          </div>
        </Form.Item>
        {createdShare?.password && (
          <Form.Item label={t('Password')}>
        <div style={{ display: 'flex', gap: 8 }}>
          <Input readOnly value={createdShare.password} style={{ flex: 1 }} />
          <Button icon={<CopyOutlined />} onClick={() => handleCopy(createdShare.password!)}>
            {t('Copy')}
          </Button>
        </div>
          </Form.Item>
        )}
      </Form>
      <Typography.Text type="secondary">
        {t('Expires At')}: {createdShare?.expires_at ? new Date(createdShare.expires_at).toLocaleString() : t('Forever')}
      </Typography.Text>
    </div>
  );

  return (
    <Modal
      title={createdShare ? t('Share created') : t('Create Share')}
      open={open}
      onOk={createdShare ? onOk : handleOk}
      onCancel={onCancel}
      confirmLoading={loading}
      destroyOnHidden
      okText={createdShare ? t('Done') : t('Create')}
    >
      {createdShare ? renderSuccess() : renderForm()}
    </Modal>
  );
});
