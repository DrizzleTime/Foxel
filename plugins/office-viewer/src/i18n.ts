type Dict = Record<string, string>;

const zh: Dict = {
  'Failed to load document link': '加载文档链接失败',
  'Preparing document...': '正在准备文档...',
  'Unable to load document': '无法加载文档',
  'Invalid document link': '文档链接无效',
  'Failed to generate an online preview link for the document.': '未能成功生成文档的在线查看链接。',
  'Close': '关闭',
};

const i18n = window.__FOXEL_EXTERNALS__.i18n!;
export const { t, useI18n } = i18n.create({ zh });
