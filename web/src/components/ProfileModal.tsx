import { memo, useEffect, useState } from 'react';
import { Modal, Form, Input, message, Collapse } from 'antd';
import { useAuth } from '../contexts/AuthContext';
import { authApi } from '../api/auth';
import { useI18n } from '../i18n';

export interface ProfileModalProps {
  open: boolean;
  onClose: () => void;
}

const ProfileModal = memo(function ProfileModal({ open, onClose }: ProfileModalProps) {
  const { user, refreshUser } = useAuth();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const { t } = useI18n();

  useEffect(() => {
    if (open && user) {
      form.setFieldsValue({
        username: user.username || '',
        full_name: user.full_name || '',
        email: user.email || '',
        old_password: '',
        new_password: '',
      });
    } else if (!open) {
      form.resetFields();
    }
  }, [open, user, form]);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      const payload: any = {};
      if (values.full_name !== (user?.full_name || '')) payload.full_name = values.full_name || null;
      if (values.email !== (user?.email || '')) payload.email = values.email || null;
      if (values.old_password || values.new_password) {
        payload.old_password = values.old_password || '';
        payload.new_password = values.new_password || '';
      }
      setLoading(true);
      await authApi.updateMe(payload);
      await refreshUser();
      message.success(t('Saved successfully'));
      onClose();
    } catch (e) {
      if (e instanceof Error) {
        message.error(e.message || t('Save failed'));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      title={t('Profile')}
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={loading}
      okText={t('Save')}
      cancelText={t('Cancel')}
    >
      <Form form={form} layout="vertical">
        <Form.Item name="username" label={t('Username')}>
          <Input disabled />
        </Form.Item>
        <Form.Item name="full_name" label={t('Full Name')}>
          <Input placeholder={t('Full Name')} />
        </Form.Item>
        <Form.Item name="email" label={t('Email')}>
          <Input placeholder={t('Email')} type="email" />
        </Form.Item>
        <Collapse
          size="small"
          items={[{
            key: 'pwd',
            label: t('Change Password'),
            children: (
              <>
                <Form.Item
                  name="old_password"
                  label={t('Old Password')}
                  dependencies={["new_password"]}
                  rules={[{
                    validator: async (_, value) => {
                      const newPwd = form.getFieldValue('new_password');
                      if ((value && !newPwd) || (!value && newPwd)) {
                        throw new Error(t('Please fill both old and new password'));
                      }
                    }
                  }]}
                >
                  <Input.Password placeholder={t('Old Password')} autoComplete="current-password" />
                </Form.Item>
                <Form.Item
                  name="new_password"
                  label={t('New Password')}
                  dependencies={["old_password"]}
                  rules={[{
                    validator: async (_, value) => {
                      const oldPwd = form.getFieldValue('old_password');
                      if ((value && !oldPwd) || (!value && oldPwd)) {
                        throw new Error(t('Please fill both old and new password'));
                      }
                    }
                  }]}
                >
                  <Input.Password placeholder={t('New Password')} autoComplete="new-password" />
                </Form.Item>
              </>
            )
          }]} />
      </Form>
    </Modal>
  );
});

export default ProfileModal;
