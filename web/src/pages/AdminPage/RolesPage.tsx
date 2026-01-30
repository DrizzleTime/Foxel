import { memo, useState, useEffect, useCallback } from 'react';
import {
  Table, Button, Space, Drawer, Form, Input, Switch, message,
  Tag, Popconfirm, Checkbox, Collapse, Typography, InputNumber, Divider
} from 'antd';
import { LockOutlined, FolderOutlined } from '@ant-design/icons';
import PageCard from '../../components/PageCard';
import { rolesApi, type PathRuleCreate, type PathRuleInfo, type RoleDetail, type RoleInfo } from '../../api/roles';
import { permissionsApi, type PermissionInfo } from '../../api/permissions';
import { useI18n } from '../../i18n';

const RolesPage = memo(function RolesPage() {
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [permissions, setPermissions] = useState<PermissionInfo[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<RoleDetail | null>(null);
  const [pathRules, setPathRules] = useState<PathRuleInfo[]>([]);
  const [form] = Form.useForm();
  const [ruleForm] = Form.useForm();
  const [ruleDrawerOpen, setRuleDrawerOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<PathRuleInfo | null>(null);
  const { t } = useI18n();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [roleList, permList] = await Promise.all([
        rolesApi.list(),
        permissionsApi.listAll(),
      ]);
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

  const openCreate = () => {
    setEditing(null);
    setPathRules([]);
    form.resetFields();
    form.setFieldsValue({
      name: '',
      description: '',
      permissions: [],
    });
    setOpen(true);
  };

  const openEdit = async (rec: RoleInfo) => {
    try {
      setLoading(true);
      const [detail, rules] = await Promise.all([
        rolesApi.get(rec.id),
        rolesApi.getPathRules(rec.id),
      ]);
      setEditing(detail);
      setPathRules(rules);
      form.resetFields();
      form.setFieldsValue({
        name: detail.name,
        description: detail.description || '',
        permissions: detail.permissions,
      });
      setOpen(true);
    } catch (e: any) {
      message.error(e.message || t('Load failed'));
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      if (editing) {
        // 更新角色
        await rolesApi.update(editing.id, {
          name: values.name.trim(),
          description: values.description || null,
        });
        // 更新权限
        await rolesApi.setPermissions(editing.id, values.permissions || []);
        message.success(t('Updated successfully'));
      } else {
        // 创建角色
        const newRole = await rolesApi.create({
          name: values.name.trim(),
          description: values.description || null,
        });
        // 设置权限
        if (values.permissions?.length) {
          await rolesApi.setPermissions(newRole.id, values.permissions);
        }
        message.success(t('Created successfully'));
      }

      setOpen(false);
      setEditing(null);
      fetchData();
    } catch (e: any) {
      if (e?.errorFields) return;
      message.error(e.message || t('Operation failed'));
    } finally {
      setLoading(false);
    }
  };

  const doDelete = async (rec: RoleInfo) => {
    try {
      await rolesApi.remove(rec.id);
      message.success(t('Deleted'));
      fetchData();
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  // 路径规则管理
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
    if (!editing) return;
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
        await rolesApi.addPathRule(editing.id, ruleData);
        message.success(t('Created successfully'));
      }

      // 刷新规则列表
      const rules = await rolesApi.getPathRules(editing.id);
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
    if (!editing) return;
    try {
      await rolesApi.deletePathRule(rule.id);
      message.success(t('Deleted'));
      const rules = await rolesApi.getPathRules(editing.id);
      setPathRules(rules);
    } catch (e: any) {
      message.error(e.message || t('Delete failed'));
    }
  };

  // 按分类分组权限
  const groupedPermissions = permissions.reduce((acc, p) => {
    if (!acc[p.category]) acc[p.category] = [];
    acc[p.category].push(p);
    return acc;
  }, {} as Record<string, PermissionInfo[]>);

  const columns = [
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
          <Button size="small" onClick={() => openEdit(rec)}>{t('Edit')}</Button>
          {!rec.is_system && (
            <Popconfirm title={t('Confirm delete?')} onConfirm={() => doDelete(rec)}>
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

  return (
    <PageCard
      title={t('Role Management')}
      extra={
        <Space>
          <Button onClick={fetchData} loading={loading}>{t('Refresh')}</Button>
          <Button type="primary" onClick={openCreate}>{t('Create Role')}</Button>
        </Space>
      }
    >
      <Table
        rowKey="id"
        dataSource={roles}
        columns={columns as any}
        loading={loading}
        pagination={false}
        style={{ marginBottom: 0 }}
      />

      {/* 角色编辑抽屉 */}
      <Drawer
        title={editing ? `${t('Edit')}: ${editing.name}` : t('Create Role')}
        width={600}
        open={open}
        onClose={() => { setOpen(false); setEditing(null); }}
        destroyOnHidden
        extra={
          <Space>
            <Button onClick={() => { setOpen(false); setEditing(null); }}>{t('Cancel')}</Button>
            <Button type="primary" onClick={submit} loading={loading}>{t('Submit')}</Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={t('Role Name')}
            rules={[{ required: true, message: t('Please input {label}', { label: t('Role Name') }) }]}
          >
            <Input placeholder={t('Role Name')} disabled={editing?.is_system} />
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

          {editing && (
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
            </>
          )}
        </Form>
      </Drawer>

      {/* 路径规则编辑抽屉 */}
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

export default RolesPage;
