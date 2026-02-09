import { Form, Input, Modal } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { memo } from 'react';
import { useI18n } from '../../../i18n';

export interface QuickCreateRoleModalProps {
  open: boolean;
  loading: boolean;
  form: FormInstance;
  onCancel: () => void;
  onOk: () => void;
}

export const QuickCreateRoleModal = memo(function QuickCreateRoleModal({
  open,
  loading,
  form,
  onCancel,
  onOk,
}: QuickCreateRoleModalProps) {
  const { t } = useI18n();
  return (
    <Modal
      title={t('Create Role')}
      open={open}
      onCancel={onCancel}
      okText={t('Submit')}
      cancelText={t('Cancel')}
      confirmLoading={loading}
      onOk={onOk}
      destroyOnHidden
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="name"
          label={t('Role Name')}
          rules={[{ required: true, message: t('Please input {label}', { label: t('Role Name') }) }]}
        >
          <Input placeholder={t('Role Name')} />
        </Form.Item>
        <Form.Item name="description" label={t('Description')}>
          <Input.TextArea placeholder={t('Description')} rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  );
});

