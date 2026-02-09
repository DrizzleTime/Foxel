import { LockOutlined } from '@ant-design/icons';
import { Button, Popconfirm, Space, Table, Tag } from 'antd';
import type { TableColumnsType } from 'antd';
import { memo, useMemo } from 'react';
import type { RoleInfo } from '../../../api/roles';
import { useI18n } from '../../../i18n';

export interface RolesTableProps {
  data: RoleInfo[];
  loading: boolean;
  onEdit: (role: RoleInfo) => void;
  onDelete: (role: RoleInfo) => void;
}

export const RolesTable = memo(function RolesTable({
  data,
  loading,
  onEdit,
  onDelete,
}: RolesTableProps) {
  const { t } = useI18n();

  const columns: TableColumnsType<RoleInfo> = useMemo(() => [
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
          <Button size="small" onClick={() => onEdit(rec)}>{t('Edit')}</Button>
          {!rec.is_system && (
            <Popconfirm title={t('Confirm delete?')} onConfirm={() => onDelete(rec)}>
              <Button size="small" danger>{t('Delete')}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ], [onDelete, onEdit, t]);

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

