/**
 * 信息面板组件
 */
import React, { CSSProperties } from 'react';
import { Typography } from 'antd';
import { SectionTitle } from './SectionTitle';
import { InfoRows } from './InfoRows';
import { HistogramPlot } from './HistogramPlot';
import type { Histogram } from '../type';

interface InfoItem {
  label: string;
  value: string | number | null;
  icon?: React.ReactNode;
}

interface InfoPanelProps {
  style?: CSSProperties;
  histogramCardStyle?: CSSProperties;
  title: string;
  captureTime: string | null;
  basicList: InfoItem[];
  shootingList: InfoItem[];
  deviceList: InfoItem[];
  miscList: InfoItem[];
  histogram: Histogram | null;
}

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
}) => {
  return (
    <aside style={style}>
      <Typography.Title level={3} style={{ color: '#fff', marginTop: 6, wordBreak: 'break-all' }}>
        {title}
      </Typography.Title>
      {captureTime && (
        <Typography.Text style={{ color: 'rgba(255,255,255,0.6)' }}>
          {`拍摄时间 ${captureTime}`}
        </Typography.Text>
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
};
