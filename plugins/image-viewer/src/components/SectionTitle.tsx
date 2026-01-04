/**
 * 章节标题组件
 */
import React from 'react';
import { Typography } from 'antd';

interface SectionTitleProps {
  children: React.ReactNode;
}

export const SectionTitle: React.FC<SectionTitleProps> = ({ children }) => {
  return (
    <Typography.Title
      level={5}
      style={{ color: '#fff', fontSize: 15, marginTop: 24, marginBottom: 12 }}
    >
      {children}
    </Typography.Title>
  );
};

