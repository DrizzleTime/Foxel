import { Modal, Spin } from 'antd';
import { CheckCircleFilled, CloseCircleFilled, ClockCircleOutlined } from '@ant-design/icons';
import { useI18n } from '../../../../i18n';
import type { BatchProgressState } from '../../hooks/useFileActions';

interface BatchProgressModalProps {
  state: BatchProgressState;
  onClose: () => void;
}

export function BatchProgressModal({ state, onClose }: BatchProgressModalProps) {
  const { t } = useI18n();
  const failedCount = state.items.filter(i => i.status === 'error').length;

  return (
    <Modal
      title={state.title}
      open={state.open}
      onCancel={onClose}
      footer={failedCount > 0
        ? <span style={{ color: 'var(--ant-color-error, #ff4d4f)' }}>{t('{failed} failed', { failed: failedCount })}</span>
        : null}
      width={420}
    >
      <div style={{ maxHeight: 320, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {state.items.map(item => (
          <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 10, minHeight: 28 }}>
            {item.status === 'success' && <CheckCircleFilled style={{ color: 'var(--ant-color-success, #52c41a)', fontSize: 16, flexShrink: 0 }} />}
            {item.status === 'error' && <CloseCircleFilled style={{ color: 'var(--ant-color-error, #ff4d4f)', fontSize: 16, flexShrink: 0 }} />}
            {item.status === 'running' && <Spin size="small" style={{ flexShrink: 0 }} />}
            {item.status === 'queued' && <ClockCircleOutlined style={{ color: 'var(--ant-color-text-tertiary, #999)', fontSize: 16, flexShrink: 0 }} />}
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: 13 }}>{item.label}</div>
              {item.status === 'error' && item.error && (
                <div style={{ color: 'var(--ant-color-error, #ff4d4f)', fontSize: 12 }}>{item.error}</div>
              )}
              {item.status === 'queued' && (
                <div style={{ color: 'var(--ant-color-text-tertiary, #999)', fontSize: 12 }}>{t('Task queued')}</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
}
