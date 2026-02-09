import React from 'react';
import { Typography, theme } from 'antd';
import { FolderOpenOutlined } from '@ant-design/icons';
import { useI18n } from '../../../i18n';

interface Props {
  isRoot: boolean;
}

export const EmptyState: React.FC<Props> = ({ isRoot }) => {
  const { token } = theme.useToken();
  const { t } = useI18n();
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', padding:isRoot? '80px 40px':'60px 40px', minHeight: isRoot? '400px':'300px', color: token.colorTextSecondary }}>
      <FolderOpenOutlined style={{ fontSize:64, color: token.colorTextQuaternary, marginBottom:16 }} />
      <Typography.Title level={4} style={{ color: token.colorTextSecondary, marginBottom:8, fontWeight:400 }}>
        {isRoot ? t('No files yet here') : t('This folder is empty')}
      </Typography.Title>
      <Typography.Text style={{ color: token.colorTextTertiary, marginBottom:24, textAlign:'center', maxWidth:300, lineHeight:1.5 }}>
        {isRoot ? t('Start uploading files or create folders to organize your content') : t('You can create folders or upload files here')}
      </Typography.Text>
    </div>
  );
};
