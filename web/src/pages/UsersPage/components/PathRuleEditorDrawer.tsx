import { Button, Checkbox, Divider, Drawer, Form, Input, InputNumber, Space, Switch } from 'antd';
import type { FormInstance } from 'antd/es/form';
import { memo } from 'react';
import type { PathRuleInfo } from '../../../api/roles';
import { useI18n } from '../../../i18n';

export interface PathRuleEditorDrawerProps {
  open: boolean;
  loading: boolean;
  editingRule: PathRuleInfo | null;
  form: FormInstance;
  onClose: () => void;
  onSubmit: () => void;
}

export const PathRuleEditorDrawer = memo(function PathRuleEditorDrawer({
  open,
  loading,
  editingRule,
  form,
  onClose,
  onSubmit,
}: PathRuleEditorDrawerProps) {
  const { t } = useI18n();
  return (
    <Drawer
      title={editingRule ? t('Edit Path Rule') : t('Add Path Rule')}
      width={400}
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
          name="path_pattern"
          label={t('Path Pattern')}
          rules={[{ required: true, message: t('Please input {label}', { label: t('Path Pattern') }) }]}
          extra={t('Use * for single level, ** for any level. Example: /photos/** matches all files in photos folder.')}
        >
          <Input placeholder="/photos/**" />
        </Form.Item>
        <Form.Item name="is_regex" label={t('Is Regex')} valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item name="priority" label={t('Priority')} extra={t('Higher value = higher priority')}>
          <InputNumber style={{ width: '100%' }} />
        </Form.Item>
        <Divider>{t('Permissions')}</Divider>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Form.Item name="can_read" valuePropName="checked" noStyle>
            <Checkbox>{t('Read')} - {t('Download and preview files')}</Checkbox>
          </Form.Item>
          <Form.Item name="can_write" valuePropName="checked" noStyle>
            <Checkbox>{t('Write')} - {t('Upload and modify files')}</Checkbox>
          </Form.Item>
          <Form.Item name="can_delete" valuePropName="checked" noStyle>
            <Checkbox>{t('Delete')} - {t('Delete files and folders')}</Checkbox>
          </Form.Item>
          <Form.Item name="can_share" valuePropName="checked" noStyle>
            <Checkbox>{t('Share')} - {t('Create share links')}</Checkbox>
          </Form.Item>
        </Space>
      </Form>
    </Drawer>
  );
});

