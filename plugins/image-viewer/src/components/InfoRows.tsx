/**
 * 信息行组件
 */
import React from 'react';

interface InfoItem {
  label: string;
  value: string | number | null;
  icon?: React.ReactNode;
}

interface InfoRowsProps {
  items: InfoItem[];
}

export const InfoRows: React.FC<InfoRowsProps> = ({ items }) => {
  const filtered = items.filter(
    item => item.value !== null && item.value !== undefined && item.value !== ''
  );

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', rowGap: 10, columnGap: 12 }}>
      {filtered.map(item => (
        <React.Fragment key={item.label}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              color: 'rgba(255,255,255,0.55)',
            }}
          >
            {item.icon && <span style={{ display: 'inline-flex', alignItems: 'center' }}>{item.icon}</span>}
            <span>{item.label}</span>
          </span>
          <span style={{ color: '#fff', wordBreak: 'break-all' }}>{item.value}</span>
        </React.Fragment>
      ))}
    </div>
  );
};

