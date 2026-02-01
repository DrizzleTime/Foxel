import { DeleteOutlined, EditOutlined, EyeOutlined, ShareAltOutlined } from '@ant-design/icons';
import { Button, Space, Tooltip } from 'antd';
import { memo, type ReactNode } from 'react';
import { useI18n } from '../../../i18n';

interface IconButtonProps {
  enabled: boolean;
  title: string;
  icon: ReactNode;
  color: string;
}

function IconButton({ enabled, title, icon, color }: IconButtonProps) {
  const button = (
    <Button
      type="text"
      size="small"
      icon={icon}
      disabled={!enabled}
      style={enabled ? { color } : undefined}
    />
  );
  return (
    <Tooltip title={title}>
      {enabled ? button : <span>{button}</span>}
    </Tooltip>
  );
}

export interface RulePermissionIconsProps {
  canRead: boolean;
  canWrite: boolean;
  canDelete: boolean;
  canShare: boolean;
}

export const RulePermissionIcons = memo(function RulePermissionIcons({
  canRead,
  canWrite,
  canDelete,
  canShare,
}: RulePermissionIconsProps) {
  const { t } = useI18n();
  return (
    <Space size={6} wrap>
      <IconButton enabled={canRead} title={t('Read')} icon={<EyeOutlined />} color="var(--ant-color-success)" />
      <IconButton enabled={canWrite} title={t('Write')} icon={<EditOutlined />} color="var(--ant-color-primary)" />
      <IconButton enabled={canDelete} title={t('Delete')} icon={<DeleteOutlined />} color="var(--ant-color-error)" />
      <IconButton enabled={canShare} title={t('Share')} icon={<ShareAltOutlined />} color="var(--ant-color-warning)" />
    </Space>
  );
});

