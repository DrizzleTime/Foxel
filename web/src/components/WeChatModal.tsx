import { Modal, theme } from 'antd';
import { useI18n } from '../i18n';

export interface WeChatModalProps {
  open: boolean;
  onClose: () => void;
}

export default function WeChatModal({ open, onClose }: WeChatModalProps) {
  const { token } = theme.useToken();
  const { t } = useI18n();

  return (
    <Modal open={open} onCancel={onClose} title={t('Join Community')} footer={null} width={320}>
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <img src="https://foxel.cc/image/wechat.png" width={200} alt="wechat" />
        <div style={{ marginTop: 12, color: token.colorTextSecondary }}>
          {t('Scan to join WeChat group')}
        </div>
        <div style={{ marginTop: 8, fontSize: 12, color: token.colorTextTertiary }}>
          {t('If QR expires, add drizzle2001 to join')}
        </div>
      </div>
    </Modal>
  );
}
