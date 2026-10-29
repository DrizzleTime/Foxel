import { Spin } from 'antd';
import { useI18n } from '../i18n';

export default function PageLoading({ fullPage = false }: { fullPage?: boolean }) {
  const { t } = useI18n();

  return (
    <div
      role="status"
      aria-label={t('Loading...')}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        height: fullPage ? '100dvh' : '100%',
        minHeight: 160,
      }}
    >
      <Spin size="large" />
    </div>
  );
}
