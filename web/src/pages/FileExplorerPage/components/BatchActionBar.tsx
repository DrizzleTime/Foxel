import { Flex, Button, theme } from 'antd';
import {
  DownloadOutlined, SwapOutlined, CopyOutlined, ShareAltOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { useI18n } from '../../../i18n';

interface BatchActionBarProps {
  count: number;
  canShare: boolean;
  onDownload: () => void;
  onMove: () => void;
  onCopy: () => void;
  onShare: () => void;
  onDelete: () => void;
}

const SAFE_AREA_PADDING = 'env(safe-area-inset-bottom, 0px)';

export function BatchActionBar({ count, canShare, onDownload, onMove, onCopy, onShare, onDelete }: BatchActionBarProps) {
  const { token } = theme.useToken();
  const { t } = useI18n();
  const disabled = count === 0;

  const actions = [
    { key: 'download', label: t('Download'), icon: <DownloadOutlined />, onClick: onDownload, disabled },
    { key: 'move', label: t('Move'), icon: <SwapOutlined />, onClick: onMove, disabled },
    { key: 'copy', label: t('Copy'), icon: <CopyOutlined />, onClick: onCopy, disabled },
    { key: 'share', label: t('Share'), icon: <ShareAltOutlined />, onClick: onShare, disabled: disabled || !canShare },
    { key: 'delete', label: t('Delete'), icon: <DeleteOutlined />, onClick: onDelete, disabled },
  ];

  return (
    <Flex
      justify="space-around"
      align="center"
      style={{
        position: 'absolute',
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 100,
        background: token.colorBgContainer,
        borderTop: `1px solid ${token.colorBorderSecondary}`,
        paddingBottom: `calc(${SAFE_AREA_PADDING} + 6px)`,
        paddingTop: 6,
        minHeight: 56,
      }}
    >
      {actions.map(action => (
        <Button
          key={action.key}
          type="text"
          disabled={action.disabled}
          onClick={action.onClick}
          style={{ height: 52, minWidth: 56, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '6px 8px' }}
        >
          <span style={{ fontSize: 20, lineHeight: 1 }}>{action.icon}</span>
          <span style={{ fontSize: 12, lineHeight: 1.2 }}>{action.label}</span>
        </Button>
      ))}
    </Flex>
  );
}
