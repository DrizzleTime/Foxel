import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import {
  Button,
  Checkbox,
  Collapse,
  Divider,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CrownOutlined,
  FolderOutlined,
  LockOutlined,
  UserOutlined,
} from '@ant-design/icons';
import PageCard from '../../components/PageCard';
import { usersApi, type UserDetail, type UserInfo } from '../../api/users';
import {
  rolesApi,
  type PathRuleCreate,
  type PathRuleInfo,
  type RoleDetail,
  type RoleInfo,
} from '../../api/roles';
import { permissionsApi, type PermissionInfo } from '../../api/permissions';
import { useI18n } from '../../i18n';

type TabKey = 'users' | 'roles';

const UsersPage = memo(function UsersPage() {
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('users');
  const [searchText, setSearchText] = useState('');

  const [users, setUsers] = useState<UserInfo[]>([]);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [permissions, setPermissions] = useState<PermissionInfo[]>([]);

  const [userDrawerOpen, setUserDrawerOpen] = useState(false);
  const [editingUser, setEditingUser] = useState<UserDetail | null>(null);
  const [userForm] = Form.useForm();

  const [roleDrawerOpen, setRoleDrawerOpen] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleDetail | null>(null);
  const [pathRules, setPathRules] = useState<PathRuleInfo[]>([]);
  const [roleUsers, setRoleUsers] = useState<UserInfo[]>([]);
  const [roleForm] = Form.useForm();

  const [ruleDrawerOpen, setRuleDrawerOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<PathRuleInfo | null>(null);
  const [ruleForm] = Form.useForm();

  const [quickRoleModalOpen, setQuickRoleModalOpen] = useState(false);
  const [quickRoleForm] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [userList, roleList, permList] = await Promise.all([
        usersApi.list(),
        rolesApi.list(),
        permissionsApi.listAll(),
      ]);
      setUsers(userList);
      setRoles(roleList);
      setPermissions(permList);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const normalizedSearch = searchText.trim().toLowerCase();
  const filteredUsers = useMemo(() => {
    if (!normalizedSearch) return users;
    return users.filter((u) => {
      const haystacks = [
        u.username,
        u.email ?? '',
        u.full_name ?? '',
      ].map(v => v.toLowerCase());
      return haystacks.some(v => v.includes(normalizedSearch));
    });
  }, [normalizedSearch, users]);
  const filteredRoles = useMemo(() => {
    if (!normalizedSearch) return roles;
    return roles.filter((r) => {
      const haystacks = [
        r.name,
        r.description ?? '',
      ].map(v => v.toLowerCase());
      return haystacks.some(v => v.includes(normalizedSearch));
    });
  }, [normalizedSearch, roles]);

  const groupedPermissions = useMemo(() => {
    return permissions.reduce((acc, p) => {
      if (!acc[p.category]) acc[p.category] = [];
      acc[p.category].push(p);
      return acc;
    }, {} as Record<string, PermissionInfo[]>);
  }, [permissions]);

  // --- User ops ---
  const openCreateUser = () => {
    setEditingUser(null);
    userForm.resetFields();
    userForm.setFieldsValue({
      username: '',
      password: '',
      email: '',
      full_name: '',
      is_admin: false,
      disabled: false,
      role_ids: [],
    });
    setUserDrawerOpen(true);
  };

  const openEditUser = async (rec: UserInfo) => {
    try {
      setLoading(true);
      const detail = await usersApi.get(rec.id);
      setEditingUser(detail);
      userForm.resetFields();
      const roleIds = roles
        .filter(r => detail.roles.includes(r.name))
        .map(r => r.id);
      userForm.setFieldsValue({
        username: detail.username,
        password: '',
        email: detail.email || '',
        full_name: detail.full_name || '',
        is_admin: detail.is_admin,
        disabled: detail.disabled,
        role_ids: roleIds,
      });
      setUserDrawerOpen(true);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  };

  const submitUser = async () => {
    try {
      const values = await userForm.validateFields();
      setLoading(true);

      if (editingUser) {
        const updateData: any = {
          email: values.email || null,
          full_name: values.full_name || null,
          is_admin: values.is_admin,
          disabled: values.disabled,
        };
        if (values.password) updateData.password = values.password;
        await usersApi.update(editingUser.id, updateData);
        await usersApi.setRoles(editingUser.id, values.role_ids || []);
        message.success(t('Updated successfully'));
      } else {
        await usersApi.create({
          username: values.username.trim(),
          password: values.password,
          email: values.email || null,
          full_name: values.full_name || null,
          is_admin: values.is_admin,
          disabled: values.disabled,
          role_ids: values.role_ids || [],
        });
        message.success(t('Created successfully'));
      }

      setUserDrawerOpen(false);
      setEditingUser(null);
      await fetchData();

      if (editingRole) {
        const nextRoleUsers = await rolesApi.getUsers(editingRole.id);
        setRoleUsers(nextRoleUsers);
      }
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  const doDeleteUser = async (rec: UserInfo) => {
    try {
      await usersApi.remove(rec.id);
      message.success(t('Deleted'));
      fetchData();
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  const handleToggleDisabled = async (rec: UserInfo, disabled: boolean) => {
    try {
      setLoading(true);
      await usersApi.update(rec.id, { disabled });
      message.success(t('Status updated'));
      fetchData();
    } catch (e: any) {
      message.error(e.message || t('Update failed'));
    } finally {
      setLoading(false);
    }
  };

  // --- Quick create role (for user drawer) ---
  const openQuickCreateRole = () => {
    quickRoleForm.resetFields();
    quickRoleForm.setFieldsValue({
      name: '',
      description: '',
    });
    setQuickRoleModalOpen(true);
  };

  const submitQuickRole = async () => {
    try {
      const values = await quickRoleForm.validateFields();
      setLoading(true);
      const newRole = await rolesApi.create({
        name: values.name.trim(),
        description: values.description || null,
      });
      message.success(t('Created successfully'));
      setRoles((prev) => [...prev, newRole].sort((a, b) => a.id - b.id));

      const currentIds = (userForm.getFieldValue('role_ids') || []) as number[];
      const nextIds = Array.from(new Set([...currentIds, newRole.id]));
      userForm.setFieldsValue({ role_ids: nextIds });

      setQuickRoleModalOpen(false);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  // --- Role ops ---
  const openCreateRole = () => {
    setEditingRole(null);
    setPathRules([]);
    setRoleUsers([]);
    roleForm.resetFields();
    roleForm.setFieldsValue({
      name: '',
      description: '',
      permissions: [],
    });
    setRoleDrawerOpen(true);
  };

  const openEditRole = async (rec: RoleInfo) => {
    try {
      setLoading(true);
      const [detail, rules, usersUsingRole] = await Promise.all([
        rolesApi.get(rec.id),
        rolesApi.getPathRules(rec.id),
        rolesApi.getUsers(rec.id),
      ]);
      setEditingRole(detail);
      setPathRules(rules);
      setRoleUsers(usersUsingRole);
      roleForm.resetFields();
      roleForm.setFieldsValue({
        name: detail.name,
        description: detail.description || '',
        permissions: detail.permissions,
      });
      setRoleDrawerOpen(true);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  };

  const submitRole = async () => {
    try {
      const values = await roleForm.validateFields();
      setLoading(true);

      if (editingRole) {
        await rolesApi.update(editingRole.id, {
          name: values.name.trim(),
          description: values.description || null,
        });
        await rolesApi.setPermissions(editingRole.id, values.permissions || []);
        message.success(t('Updated successfully'));
      } else {
        const newRole = await rolesApi.create({
          name: values.name.trim(),
          description: values.description || null,
        });
        if (values.permissions?.length) {
          await rolesApi.setPermissions(newRole.id, values.permissions);
        }
        message.success(t('Created successfully'));
      }

      setRoleDrawerOpen(false);
      setEditingRole(null);
      await fetchData();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  const doDeleteRole = async (rec: RoleInfo) => {
    try {
      await rolesApi.remove(rec.id);
      message.success(t('Deleted'));
      fetchData();
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  // --- Path rules ---
  const openAddRule = () => {
    setEditingRule(null);
    ruleForm.resetFields();
    ruleForm.setFieldsValue({
      path_pattern: '/',
      is_regex: false,
      can_read: true,
      can_write: false,
      can_delete: false,
      can_share: false,
      priority: 0,
    });
    setRuleDrawerOpen(true);
  };

  const openEditRule = (rule: PathRuleInfo) => {
    setEditingRule(rule);
    ruleForm.resetFields();
    ruleForm.setFieldsValue({
      path_pattern: rule.path_pattern,
      is_regex: rule.is_regex,
      can_read: rule.can_read,
      can_write: rule.can_write,
      can_delete: rule.can_delete,
      can_share: rule.can_share,
      priority: rule.priority,
    });
    setRuleDrawerOpen(true);
  };

  const submitRule = async () => {
    if (!editingRole) return;
    try {
      const values = await ruleForm.validateFields();
      setLoading(true);

      const ruleData: PathRuleCreate = {
        path_pattern: values.path_pattern,
        is_regex: values.is_regex,
        can_read: values.can_read,
        can_write: values.can_write,
        can_delete: values.can_delete,
        can_share: values.can_share,
        priority: values.priority,
      };

      if (editingRule) {
        await rolesApi.updatePathRule(editingRule.id, ruleData);
        message.success(t('Updated successfully'));
      } else {
        await rolesApi.addPathRule(editingRole.id, ruleData);
        message.success(t('Created successfully'));
      }

      const rules = await rolesApi.getPathRules(editingRole.id);
      setPathRules(rules);
      setRuleDrawerOpen(false);
      setEditingRule(null);
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  const deleteRule = async (rule: PathRuleInfo) => {
    if (!editingRole) return;
    try {
      await rolesApi.deletePathRule(rule.id);
      message.success(t('Deleted'));
      const rules = await rolesApi.getPathRules(editingRole.id);
      setPathRules(rules);
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  const userColumns = [
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
    { title: t('Full Name'), dataIndex: 'full_name', render: (v: string | null) => v || '-' },
    {
      title: t('Status'),
      dataIndex: 'disabled',
      width: 100,
      render: (disabled: boolean, rec: UserInfo) => (
        <Switch
          checked={!disabled}
          size="small"
          loading={loading}
          onChange={(checked) => handleToggleDisabled(rec, !checked)}
          checkedChildren={t('Active')}
          unCheckedChildren={t('Disabled')}
        />
      ),
    },
    {
      title: t('Last Login'),
      dataIndex: 'last_login',
      width: 180,
      render: (v: string | null) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: t('Actions'),
      width: 160,
      render: (_: any, rec: UserInfo) => (
        <Space size="small">
          <Button size="small" onClick={() => openEditUser(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => doDeleteUser(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const roleColumns = [
    {
      title: t('Role Name'),
      dataIndex: 'name',
      render: (value: string, rec: RoleInfo) => (
        <Space>
          <LockOutlined />
          {value}
          {rec.is_system && <Tag color="blue">{t('System')}</Tag>}
        </Space>
      ),
    },
    { title: t('Description'), dataIndex: 'description', render: (v: string | null) => v || '-' },
    {
      title: t('Created At'),
      dataIndex: 'created_at',
      width: 180,
      render: (v: string) => new Date(v).toLocaleString(),
    },
    {
      title: t('Actions'),
      width: 160,
      render: (_: any, rec: RoleInfo) => (
        <Space size="small">
          <Button size="small" onClick={() => openEditRole(rec)}>{t('Edit')}</Button>
          {!rec.is_system && (
            <Popconfirm title={t('Confirm delete?')} onConfirm={() => doDeleteRole(rec)}>
              <Button size="small" danger>{t('Delete')}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const ruleColumns = [
    {
      title: t('Path Pattern'),
      dataIndex: 'path_pattern',
      render: (v: string, rec: PathRuleInfo) => (
        <Space>
          <FolderOutlined />
          <code>{v}</code>
          {rec.is_regex && <Tag color="purple">Regex</Tag>}
        </Space>
      ),
    },
    {
      title: t('Permissions'),
      render: (_: any, rec: PathRuleInfo) => (
        <Space size={[0, 4]} wrap>
          {rec.can_read && <Tag color="green">{t('Read')}</Tag>}
          {rec.can_write && <Tag color="blue">{t('Write')}</Tag>}
          {rec.can_delete && <Tag color="red">{t('Delete')}</Tag>}
          {rec.can_share && <Tag color="orange">{t('Share')}</Tag>}
        </Space>
      ),
    },
    {
      title: t('Priority'),
      dataIndex: 'priority',
      width: 80,
    },
    {
      title: t('Actions'),
      width: 140,
      render: (_: any, rec: PathRuleInfo) => (
        <Space size="small">
          <Button size="small" onClick={() => openEditRule(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => deleteRule(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const roleUserColumns = [
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
        <Button size="small" onClick={() => openEditUser(rec)}>{t('Edit')}</Button>
      ),
    },
  ];

  const tabItems = [
    {
      key: 'users',
      label: `${t('Users')} (${filteredUsers.length})`,
      children: (
        <Table
          rowKey="id"
          dataSource={filteredUsers}
          columns={userColumns as any}
          loading={loading}
          pagination={false}
          style={{ marginBottom: 0 }}
        />
      ),
    },
    {
      key: 'roles',
      label: `${t('Roles')} (${filteredRoles.length})`,
      children: (
        <Table
          rowKey="id"
          dataSource={filteredRoles}
          columns={roleColumns as any}
          loading={loading}
          pagination={false}
          style={{ marginBottom: 0 }}
        />
      ),
    },
  ];

  return (
    <PageCard
      title={t('User Management')}
      extra={
        <Space>
          <Input.Search
            allowClear
            value={searchText}
            placeholder={t('Search users or roles')}
            onChange={(e) => setSearchText(e.target.value)}
            style={{ width: 260 }}
          />
          <Button onClick={fetchData} loading={loading}>{t('Refresh')}</Button>
          <Button type="primary" onClick={() => { setActiveTab('users'); openCreateUser(); }}>
            {t('Create User')}
          </Button>
          <Button onClick={() => { setActiveTab('roles'); openCreateRole(); }}>
            {t('Create Role')}
          </Button>
        </Space>
      }
    >
      <Tabs activeKey={activeTab} onChange={(k) => setActiveTab(k as TabKey)} items={tabItems} />

      {/* User editor */}
      <Drawer
        title={editingUser ? `${t('Edit')}: ${editingUser.username}` : t('Create User')}
        width={480}
        open={userDrawerOpen}
        onClose={() => { setUserDrawerOpen(false); setEditingUser(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setUserDrawerOpen(false); setEditingUser(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submitUser} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form form={userForm} layout="vertical">
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
                <Button type="link" size="small" onClick={openQuickCreateRole}>
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

      <Modal
        title={t('Create Role')}
        open={quickRoleModalOpen}
        onCancel={() => setQuickRoleModalOpen(false)}
        okText={t('Submit')}
        cancelText={t('Cancel')}
        confirmLoading={loading}
        onOk={submitQuickRole}
        destroyOnHidden
      >
        <Form form={quickRoleForm} layout="vertical">
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

      {/* Role editor */}
      <Drawer
        title={editingRole ? `${t('Edit')}: ${editingRole.name}` : t('Create Role')}
        width={600}
        open={roleDrawerOpen}
        onClose={() => { setRoleDrawerOpen(false); setEditingRole(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setRoleDrawerOpen(false); setEditingRole(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submitRole} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form form={roleForm} layout="vertical">
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

          <Divider>{t('System Permissions')}</Divider>
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

          {editingRole && (
            <>
              <Divider>{t('Path Rules')}</Divider>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" size="small" onClick={openAddRule}>
                  {t('Add Path Rule')}
                </Button>
              </Space>
              <Table
                rowKey="id"
                dataSource={pathRules}
                columns={ruleColumns as any}
                pagination={false}
                size="small"
              />

              <Divider>{t('Users')}</Divider>
              <Table
                rowKey="id"
                dataSource={roleUsers}
                columns={roleUserColumns as any}
                pagination={false}
                size="small"
              />
            </>
          )}
        </Form>
      </Drawer>

      {/* Path rule editor */}
      <Drawer
        title={editingRule ? t('Edit Path Rule') : t('Add Path Rule')}
        width={400}
        open={ruleDrawerOpen}
        onClose={() => { setRuleDrawerOpen(false); setEditingRule(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setRuleDrawerOpen(false); setEditingRule(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submitRule} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form form={ruleForm} layout="vertical">
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
    </PageCard>
  );
});

export default UsersPage;
