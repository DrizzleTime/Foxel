type Dict = Record<string, string>;

const zh: Dict = {
  'Failed to get temporary link': '获取临时链接失败',
  'Loading PDF...': '正在加载 PDF...',
  'Unable to load PDF': '无法加载 PDF',
  'No available link': '无可用链接',
  'Failed to generate a temporary access link for the PDF.': '未能生成 PDF 的临时访问链接',
  'Close': '关闭',
};

const i18n = window.__FOXEL_EXTERNALS__.i18n!;
export const { t, useI18n } = i18n.create({ zh });
