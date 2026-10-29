import type { ReactNode } from 'react';
import { Button, Drawer, Space, Tooltip, theme } from 'antd';
import { CloseOutlined, FormOutlined } from '@ant-design/icons';
import { useI18n } from '../i18n';
import '../styles/ai-agent-drawer.css';

interface AiAgentDrawerProps {
  open: boolean;
  width: string;
  onClose(): void;
  onClear?(): void;
  clearDisabled?: boolean;
  afterOpenChange?(visible: boolean): void;
  children: ReactNode;
}

export default function AiAgentDrawer({ open, width, onClose, onClear, clearDisabled = true, afterOpenChange, children }: AiAgentDrawerProps) {
  const { t } = useI18n();
  const { token } = theme.useToken();

  return (
    <Drawer
      title={(
        <div className="fx-agent-header">
          <span className="fx-agent-heading">{t('AI Agent')}</span>
          <Space size={2}>
            <Tooltip title={t('Clear')}>
              <Button
                type="text"
                icon={<FormOutlined />}
                aria-label={t('Clear')}
                onClick={onClear}
                disabled={clearDisabled}
              />
            </Tooltip>
            <Tooltip title={t('Close')}>
              <Button
                type="text"
                icon={<CloseOutlined />}
                aria-label={t('Close')}
                onClick={onClose}
              />
            </Tooltip>
          </Space>
        </div>
      )}
      closable={false}
      open={open}
      onClose={onClose}
      placement="right"
      size={width}
      mask={false}
      push={false}
      aria-modal={false}
      autoFocus={false}
      focusable={{ trap: false }}
      afterOpenChange={afterOpenChange}
      destroyOnHidden
      styles={{
        wrapper: {
          boxShadow: 'none',
        },
        section: {
          borderLeft: `1px solid ${token.colorBorderSecondary}`,
          background: token.colorBgLayout,
        },
        header: {
          minHeight: 56,
          padding: '10px 16px',
          borderBottom: 0,
        },
        body: {
          padding: '0 12px 12px',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        },
      }}
    >
      {children}
    </Drawer>
  );
}
