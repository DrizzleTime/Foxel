import { CrownOutlined, UserOutlined } from '@ant-design/icons';
import { Button, Popconfirm, Space, Switch, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { memo, useMemo } from 'react';
import type { UserInfo } from '../../../api/users';
import { useI18n } from '../../../i18n';

export interface UsersTableProps {
  data: UserInfo[];
  loading: boolean;
  onEdit: (user: UserInfo) => void;
  onDelete: (user: UserInfo) => void;
  onToggleDisabled: (user: UserInfo, disabled: boolean) => void;
}

export const UsersTable = memo(function UsersTable({
  data,
  loading,
  onEdit,
  onDelete,
  onToggleDisabled,
}: UsersTableProps) {
  const { t } = useI18n();

  const columns: TableColumnsType<UserInfo> = useMemo(() => [
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
          onChange={(checked) => onToggleDisabled(rec, !checked)}
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
          <Button size="small" onClick={() => onEdit(rec)}>{t('Edit')}</Button>
          <Popconfirm title={t('Confirm delete?')} onConfirm={() => onDelete(rec)}>
            <Button size="small" danger>{t('Delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ], [loading, onDelete, onEdit, onToggleDisabled, t]);

  return (
    <Table
      rowKey="id"
      dataSource={data}
      columns={columns}
      loading={loading}
      pagination={false}
      style={{ marginBottom: 0 }}
    />
  );
});

