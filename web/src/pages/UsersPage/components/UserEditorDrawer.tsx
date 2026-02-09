import { Button, Drawer, Form, Input, Select, Space, Switch, Typography } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { memo } from 'react';
import type { RoleInfo } from '../../../api/roles';
import type { UserDetail } from '../../../api/users';
import { useI18n } from '../../../i18n';

export interface UserEditorDrawerProps {
  open: boolean;
  loading: boolean;
  editingUser: UserDetail | null;
  form: FormInstance;
  roles: RoleInfo[];
  onClose: () => void;
  onSubmit: () => void;
  onOpenQuickCreateRole: () => void;
}

export const UserEditorDrawer = memo(function UserEditorDrawer({
  open,
  loading,
  editingUser,
  form,
  roles,
  onClose,
  onSubmit,
  onOpenQuickCreateRole,
}: UserEditorDrawerProps) {
  const { t } = useI18n();
  return (
    <Drawer
      title={editingUser ? `${t('Edit')}: ${editingUser.username}` : t('Create User')}
      width={480}
      open={open}
      onClose={onClose}
      destroyOnHidden
      extra={
        <Space>
          <Button onClick={onClose}>{t('Cancel')}</Button>
          <Button type="primary" onClick={onSubmit} loading={loading}>{t('Submit')}</Button>
        </Space>
      }
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="username"
          label={t('Username')}
          rules={[{ required: true, message: t('Please input {label}', { label: t('Username') }) }]}
        >
          <Input placeholder={t('Username')} disabled={!!editingUser} />
        </Form.Item>
        <Form.Item
          name="password"
          label={editingUser ? t('New Password (leave empty to keep current)') : t('Password')}
          rules={editingUser ? [] : [{ required: true, message: t('Please input {label}', { label: t('Password') }) }]}
        >
          <Input.Password placeholder={t('Password')} />
        </Form.Item>
        <Form.Item name="email" label={t('Email')}>
          <Input placeholder={t('Email')} />
        </Form.Item>
        <Form.Item name="full_name" label={t('Full Name')}>
          <Input placeholder={t('Full Name')} />
        </Form.Item>
        <Form.Item
          name="role_ids"
          label={(
            <Space size={4}>
              {t('Roles')}
              <Button type="link" size="small" onClick={onOpenQuickCreateRole}>
                {t('Quick Create Role')}
              </Button>
            </Space>
          )}
        >
          <Select
            mode="multiple"
            placeholder={t('Select roles')}
            options={roles.map(r => ({
              value: r.id,
              label: r.name + (r.is_system ? ` (${t('System')})` : ''),
            }))}
          />
        </Form.Item>
        <Form.Item name="is_admin" label={t('Super Admin')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="disabled" label={t('Disabled')} valuePropName="checked">
          <Switch />
        </Form.Item>
        {editingUser && (
          <Typography.Text type="secondary">
            {t('Created by')}: {editingUser.created_by_username || '-'}
          </Typography.Text>
        )}
      </Form>
    </Drawer>
  );
});

