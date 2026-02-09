import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { Button, Form, Input, Space, Tabs, message } from 'antd';
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
import { RolesTable } from './components/RolesTable';
import { RoleEditorDrawer } from './components/RoleEditorDrawer';
import { PathRuleEditorDrawer } from './components/PathRuleEditorDrawer';
import { QuickCreateRoleModal } from './components/QuickCreateRoleModal';
import { UserEditorDrawer } from './components/UserEditorDrawer';
import { UsersTable } from './components/UsersTable';
import type { RoleDrawerTab } from './types';

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
  const [roleDrawerTab, setRoleDrawerTab] = useState<RoleDrawerTab>('basic');
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
    setRoleDrawerTab('basic');
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
      setRoleDrawerTab('basic');
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

  const closeUserDrawer = () => {
    setUserDrawerOpen(false);
    setEditingUser(null);
  };

  const closeRoleDrawer = () => {
    setRoleDrawerOpen(false);
    setEditingRole(null);
    setRoleDrawerTab('basic');
  };

  const closeRuleDrawer = () => {
    setRuleDrawerOpen(false);
    setEditingRule(null);
  };

  const closeQuickRoleModal = () => {
    setQuickRoleModalOpen(false);
  };

  const tabItems = [
    {
      key: 'users',
      label: `${t('Users')} (${filteredUsers.length})`,
      children: (
        <UsersTable
          data={filteredUsers}
          loading={loading}
          onEdit={openEditUser}
          onDelete={doDeleteUser}
          onToggleDisabled={handleToggleDisabled}
        />
      ),
    },
    {
      key: 'roles',
      label: `${t('Roles')} (${filteredRoles.length})`,
      children: (
        <RolesTable
          data={filteredRoles}
          loading={loading}
          onEdit={openEditRole}
          onDelete={doDeleteRole}
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

      <UserEditorDrawer
        open={userDrawerOpen}
        loading={loading}
        editingUser={editingUser}
        form={userForm}
        roles={roles}
        onClose={closeUserDrawer}
        onSubmit={submitUser}
        onOpenQuickCreateRole={openQuickCreateRole}
      />

      <QuickCreateRoleModal
        open={quickRoleModalOpen}
        loading={loading}
        form={quickRoleForm}
        onCancel={closeQuickRoleModal}
        onOk={submitQuickRole}
      />

      <RoleEditorDrawer
        open={roleDrawerOpen}
        loading={loading}
        editingRole={editingRole}
        form={roleForm}
        activeTab={roleDrawerTab}
        onTabChange={setRoleDrawerTab}
        groupedPermissions={groupedPermissions}
        pathRules={pathRules}
        roleUsers={roleUsers}
        onAddPathRule={openAddRule}
        onEditPathRule={openEditRule}
        onDeletePathRule={deleteRule}
        onEditUser={openEditUser}
        onClose={closeRoleDrawer}
        onSubmit={submitRole}
      />

      <PathRuleEditorDrawer
        open={ruleDrawerOpen}
        loading={loading}
        editingRule={editingRule}
        form={ruleForm}
        onClose={closeRuleDrawer}
        onSubmit={submitRule}
      />
    </PageCard>
  );
});

export default UsersPage;
