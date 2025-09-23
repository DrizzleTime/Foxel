import type { ReactNode } from 'react';

export interface HistogramData {
  r: number[];
  g: number[];
  b: number[];
}

export interface RgbColor {
  r: number;
  g: number;
  b: number;
}

export interface InfoItem {
  label: string;
  value: string | number | null;
  icon?: ReactNode;
}
