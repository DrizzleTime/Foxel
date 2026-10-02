import { Button, Modal, QRCode, theme } from 'antd';
import { SendOutlined, WechatOutlined } from '@ant-design/icons';
import { useI18n } from '../i18n';

export interface CommunityModalProps {
  open: boolean;
  onClose: () => void;
}

const TELEGRAM_URL = 'https://t.me/+thDsBfyqJxZkNTU1';

export default function CommunityModal({ open, onClose }: CommunityModalProps) {
  const { token } = theme.useToken();
  const { t } = useI18n();

  return (
    <Modal open={open} onCancel={onClose} title={t('Join Community')} footer={null} width={600}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 24, padding: '16px 0', textAlign: 'center' }}>
        <section style={{ minWidth: 0 }}>
          <h3 style={{ fontSize: 16, margin: '0 0 16px' }}><WechatOutlined style={{ marginRight: 8 }} />{t('WeChat')}</h3>
          <div style={{ height: 200, display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <img src="https://foxel.cc/image/wechat.png" width={200} height={200} style={{ objectFit: 'contain', maxWidth: '100%' }} alt={t('Scan to join WeChat group')} />
          </div>
          <div style={{ marginTop: 16, color: token.colorTextSecondary }}>
            {t('Scan to join WeChat group')}
          </div>
          <div style={{ marginTop: 8, fontSize: 12, color: token.colorTextTertiary, overflowWrap: 'anywhere' }}>
            {t('If QR expires, add drizzle2001 to join')}
          </div>
        </section>
        <section style={{ minWidth: 0 }}>
          <h3 style={{ fontSize: 16, margin: '0 0 16px' }}><SendOutlined style={{ marginRight: 8 }} />Telegram</h3>
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <QRCode value={TELEGRAM_URL} size={200} color="#111111" bgColor="#ffffff" />
          </div>
          <Button style={{ marginTop: 16 }} icon={<SendOutlined />} href={TELEGRAM_URL} target="_blank" rel="noopener noreferrer">
            {t('Join Telegram group')}
          </Button>
        </section>
      </div>
    </Modal>
  );
}
