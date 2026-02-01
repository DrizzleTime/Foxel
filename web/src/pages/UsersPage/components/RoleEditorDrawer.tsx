import { CrownOutlined, FolderOutlined, UserOutlined } from '@ant-design/icons';
import {
  Button,
  Checkbox,
  Collapse,
  Drawer,
  Form,
  Input,
  Popconfirm,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd';
import type { FormInstance } from 'antd/es/form';
import type { TableColumnsType, TabsProps } from 'antd';
import { memo, useMemo } from 'react';
import type { PathRuleInfo, RoleDetail } from '../../../api/roles';
import type { UserInfo } from '../../../api/users';
import type { PermissionInfo } from '../../../api/permissions';
import { useI18n } from '../../../i18n';
import { RulePermissionIcons } from './RulePermissionIcons';
import type { RoleDrawerTab } from '../types';

export interface RoleEditorDrawerProps {
  open: boolean;
  loading: boolean;
  editingRole: RoleDetail | null;
  form: FormInstance;
  activeTab: RoleDrawerTab;
  onTabChange: (tab: RoleDrawerTab) => void;
  groupedPermissions: Record<string, PermissionInfo[]>;
  pathRules: PathRuleInfo[];
  roleUsers: UserInfo[];
  onAddPathRule: () => void;
  onEditPathRule: (rule: PathRuleInfo) => void;
  onDeletePathRule: (rule: PathRuleInfo) => void;
  onEditUser: (user: UserInfo) => void;
  onClose: () => void;
  onSubmit: () => void;
}

export const RoleEditorDrawer = memo(function RoleEditorDrawer({
  open,
  loading,
  editingRole,
  form,
  activeTab,
  onTabChange,
  groupedPermissions,
  pathRules,
  roleUsers,
  onAddPathRule,
  onEditPathRule,
  onDeletePathRule,
  onEditUser,
  onClose,
  onSubmit,
}: RoleEditorDrawerProps) {
  const { t } = useI18n();

  const ruleColumns: TableColumnsType<PathRuleInfo> = useMemo(() => [
    {
      title: t('Path Pattern'),
      dataIndex: 'path_pattern',
      render: (v: string, rec: PathRuleInfo) => (
        <Space>
          <FolderOutlined />
          <code>{v}</code>
          {rec.is_regex && <Tag color="purple">{t('Regex')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('Permissions'),
      render: (_: any, rec: PathRuleInfo) => (
        <RulePermissionIcons
          canRead={rec.can_read}
          canWrite={rec.can_write}
          canDelete={rec.can_delete}
          canShare={rec.can_share}
        />
      ),
    },
    { title: t('Priority'), dataIndex: 'priority', width: 80 },
    {
      title: t('Actions'),
      width: 140,
      render: (_: any, rec: PathRuleInfo) => (
        <Space size="small">
          <Button size="small" onClick={() => onEditPathRule(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => onDeletePathRule(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], [onDeletePathRule, onEditPathRule, t]);

  const roleUserColumns: TableColumnsType<UserInfo> = useMemo(() => [
    {
      title: t('Username'),
      dataIndex: 'username',
      render: (value: string, rec: UserInfo) => (
        <Space>
          {rec.is_admin ? <CrownOutlined style={{ color: '#faad14' }} /> : <UserOutlined />}
          {value}
          {rec.is_admin && <Tag color="gold">{t('Admin')}</Tag>}
        </Space>
      ),
    },
    { title: t('Email'), dataIndex: 'email', render: (v: string | null) => v || '-' },
    {
      title: t('Status'),
      dataIndex: 'disabled',
      width: 90,
      render: (disabled: boolean) => disabled ? <Tag>{t('Disabled')}</Tag> : <Tag color="green">{t('Active')}</Tag>,
    },
    {
      title: t('Actions'),
      width: 110,
      render: (_: any, rec: UserInfo) => (
        <Button size="small" onClick={() => onEditUser(rec)}>{t('Edit')}</Button>
      ),
    },
  ], [onEditUser, t]);

  const tabItems: TabsProps['items'] = useMemo(() => {
    const items: TabsProps['items'] = [
      {
        key: 'basic',
        label: t('Basic Info'),
        children: (
          <>
            <Form.Item
              name="name"
              label={t('Role Name')}
              rules={[{ required: true, message: t('Please input {label}', { label: t('Role Name') }) }]}
            >
              <Input placeholder={t('Role Name')} disabled={editingRole?.is_system} />
            </Form.Item>
            <Form.Item name="description" label={t('Description')}>
              <Input.TextArea placeholder={t('Description')} rows={2} />
            </Form.Item>
          </>
        ),
      },
      {
        key: 'permissions',
        label: t('System Permissions'),
        children: (
          <Form.Item name="permissions" label={t('Permissions')}>
            <Checkbox.Group style={{ width: '100%' }}>
              <Collapse
                items={Object.entries(groupedPermissions).map(([category, perms]) => ({
                  key: category,
                  label: t(`permission.category.${category}`) === `permission.category.${category}`
                    ? category.charAt(0).toUpperCase() + category.slice(1)
                    : t(`permission.category.${category}`),
                  children: (
                    <Space direction="vertical" style={{ width: '100%' }}>
                      {perms.map(p => (
                        <Checkbox key={p.code} value={p.code}>
                          {p.name}
                          {p.description && (
                            <Typography.Text type="secondary" style={{ marginLeft: 8 }}>
                              {p.description}
                            </Typography.Text>
                          )}
                        </Checkbox>
                      ))}
                    </Space>
                  ),
                }))}
              />
            </Checkbox.Group>
          </Form.Item>
        ),
      },
    ];

    if (editingRole) {
      items.push(
        {
          key: 'path_rules',
          label: `${t('Path Rules')} (${pathRules.length})`,
          children: (
            <Space direction="vertical" style={{ width: '100%' }} size={12}>
              <Space>
                <Button type="primary" size="small" onClick={onAddPathRule}>
                  {t('Add Path Rule')}
                </Button>
              </Space>
              <Table
                rowKey="id"
                dataSource={pathRules}
                columns={ruleColumns}
                pagination={false}
                size="small"
                loading={loading}
              />
            </Space>
          ),
        },
        {
          key: 'users',
          label: `${t('Users')} (${roleUsers.length})`,
          children: (
            <Table
              rowKey="id"
              dataSource={roleUsers}
              columns={roleUserColumns}
              pagination={false}
              size="small"
              loading={loading}
            />
          ),
        },
      );
    }

    return items;
  }, [editingRole, groupedPermissions, loading, pathRules, roleUserColumns, roleUsers, ruleColumns, onAddPathRule, t]);

  return (
    <Drawer
      title={editingRole ? `${t('Edit')}: ${editingRole.name}` : t('Create Role')}
      width={600}
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
        <Tabs
          activeKey={activeTab}
          onChange={(k) => onTabChange(k as RoleDrawerTab)}
          destroyInactiveTabPane={false}
          items={tabItems}
        />
      </Form>
    </Drawer>
  );
});
