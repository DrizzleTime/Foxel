import React from 'react';
import { Typography, Empty } from 'antd';
import type { HistogramData, InfoItem } from './types';

interface InfoPanelProps {
  style: React.CSSProperties;
  histogramCardStyle: React.CSSProperties;
  title: string;
  captureTime: string | number | null;
  basicList: InfoItem[];
  shootingList: InfoItem[];
  deviceList: InfoItem[];
  miscList: InfoItem[];
  histogram: HistogramData | null;
}

const SectionTitle: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <Typography.Title level={5} style={{ color: '#fff', fontSize: 15, marginTop: 24, marginBottom: 12 }}>
    {children}
  </Typography.Title>
);

const HistogramPlot: React.FC<{ data: HistogramData | null }> = ({ data }) => {
  if (!data) {
    return <Empty description="无法解析直方图" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }
  const width = 260;
  const height = 140;
  const max = Math.max(...data.r, ...data.g, ...data.b, 1);
  const toPath = (arr: number[]) => arr
    .map((value, index) => {
      const x = (index / 255) * width;
      const y = height - (value / max) * height;
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ width: '100%' }}>
      <rect x={0} y={0} width={width} height={height} fill="rgba(255,255,255,0.04)" />
      <path d={toPath(data.r)} stroke="rgba(255,99,132,0.88)" fill="none" strokeWidth={1.3} />
      <path d={toPath(data.g)} stroke="rgba(75,192,192,0.88)" fill="none" strokeWidth={1.3} />
      <path d={toPath(data.b)} stroke="rgba(54,162,235,0.88)" fill="none" strokeWidth={1.3} />
    </svg>
  );
};

const InfoRows: React.FC<{ items: InfoItem[] }> = ({ items }) => (
  <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', rowGap: 10, columnGap: 12 }}>
    {items
      .filter(item => item.value !== null && item.value !== undefined && item.value !== '')
      .map(item => (
        <React.Fragment key={item.label}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, color: 'rgba(255,255,255,0.55)' }}>
            {item.icon && <span style={{ display: 'inline-flex', alignItems: 'center' }}>{item.icon}</span>}
            <span>{item.label}</span>
          </span>
          <span style={{ color: '#fff', wordBreak: 'break-all' }}>{item.value}</span>
        </React.Fragment>
      ))}
  </div>
);

export const InfoPanel: React.FC<InfoPanelProps> = ({
  style,
  histogramCardStyle,
  title,
  captureTime,
  basicList,
  shootingList,
  deviceList,
  miscList,
  histogram,
}) => (
  <aside style={style}>
    <Typography.Title level={3} style={{ color: '#fff', marginTop: 6, wordBreak: 'break-all' }}>
      {title}
    </Typography.Title>
    {captureTime && (
      <Typography.Text style={{ color: 'rgba(255,255,255,0.6)' }}>拍摄时间 {captureTime}</Typography.Text>
    )}

    <SectionTitle>基本信息</SectionTitle>
    <InfoRows items={basicList} />

    {shootingList.some(i => i.value) && (
      <>
        <SectionTitle>拍摄参数</SectionTitle>
        <InfoRows items={shootingList} />
      </>
    )}

    {deviceList.some(i => i.value) && (
      <>
        <SectionTitle>设备信息</SectionTitle>
        <InfoRows items={deviceList} />
      </>
    )}

    {miscList.some(i => i.value) && (
      <>
        <SectionTitle>其他</SectionTitle>
        <InfoRows items={miscList} />
      </>
    )}

    <SectionTitle>直方图</SectionTitle>
    <div style={histogramCardStyle}>
      <HistogramPlot data={histogram} />
      <div style={{ marginTop: 12, display: 'flex', gap: 12, fontSize: 12 }}>
        <span style={{ color: 'rgba(255,99,132,0.88)' }}>R</span>
        <span style={{ color: 'rgba(75,192,192,0.88)' }}>G</span>
        <span style={{ color: 'rgba(54,162,235,0.88)' }}>B</span>
      </div>
    </div>
  </aside>
);
