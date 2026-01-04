/**
 * 图片查看器插件私有类型定义
 */

export interface RGB {
  r: number;
  g: number;
  b: number;
}

export interface Histogram {
  r: number[];
  g: number[];
  b: number[];
}

export interface ImageStats {
  histogram: Histogram | null;
  dominantColor: RGB | null;
}
