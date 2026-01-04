/**
 * 直方图绘制组件
 */
import React from 'react';
import { Empty } from 'antd';
import type { Histogram } from '../type';

interface HistogramPlotProps {
  data: Histogram | null;
}

export const HistogramPlot: React.FC<HistogramPlotProps> = ({ data }) => {
  if (!data) {
    return <Empty description="无法解析直方图" image={Empty.PRESENTED_IMAGE_SIMPLE} />;
  }

  const width = 260;
  const height = 140;
  const max = Math.max(...data.r, ...data.g, ...data.b, 1);

  const toPath = (arr: number[]): string =>
    arr
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
