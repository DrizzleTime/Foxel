import { Dropdown, Button } from 'antd';
import { GlobalOutlined, CheckOutlined } from '@ant-design/icons';
import { memo } from 'react';
import { useI18n } from '../i18n';

const LanguageSwitcher = memo(function LanguageSwitcher() {
  const { lang, setLang, t } = useI18n();
  const items = [
    { key: 'zh', label: t('Chinese'), icon: lang === 'zh' ? <CheckOutlined /> : undefined, onClick: () => setLang('zh') },
    { key: 'en', label: t('English'), icon: lang === 'en' ? <CheckOutlined /> : undefined, onClick: () => setLang('en') },
  ];
  return (
    <Dropdown menu={{ items }} trigger={['click']}>
      <Button icon={<GlobalOutlined />}>{t('Language')}</Button>
    </Dropdown>
  );
});

export default LanguageSwitcher;

