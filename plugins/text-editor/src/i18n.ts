type Dict = Record<string, string>;

const zh: Dict = {
  'Unknown error': '未知错误',
  'Failed to load file: {error}': '加载文件失败: {error}',
  'Large file preview only first 1MB; saving disabled': '大文件仅预览前 1MB，已禁用保存',
  'Saved successfully': '保存成功',
  'Failed to save file: {error}': '保存文件失败: {error}',
  ' (Large file preview only first 1MB; editing and saving disabled)': ' （大文件仅预览前 1MB，编辑与保存已禁用）',
  'Save': '保存',
};

const i18n = window.__FOXEL_EXTERNALS__.i18n!;
export const { t, useI18n } = i18n.create({ zh });
