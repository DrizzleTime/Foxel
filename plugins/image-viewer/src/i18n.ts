type Dict = Record<string, string>;

const zh: Dict = {
  'Previous': '上一张',
  'Next': '下一张',
  'Zoom out': '缩小',
  'Zoom in': '放大',
  'Rotate 90°': '旋转 90°',
  'Reset': '重置',
  'Fit to screen': '适应窗口',

  'Failed to parse histogram': '无法解析直方图',
  'Filmstrip · {count} images': '胶片带 · {count} 张',
  'Page {page} / {totalPages}': '第 {page} 页 / 共 {totalPages} 页',
  'No images': '暂无图片',

  'Captured at {time}': '拍摄时间 {time}',
  'Basic Info': '基本信息',
  'Shooting': '拍摄参数',
  'Device': '设备信息',
  'Other': '其他',
  'Histogram': '直方图',

  'File name': '文件名',
  'File size': '文件大小',
  'Resolution': '分辨率',
  'Color space': '颜色空间',
  'Modified time': '修改时间',
  'Path': '路径',
  'Focal length': '焦距',
  'Aperture': '光圈',
  'Shutter': '快门',
  'ISO': 'ISO',
  'Camera': '相机',
  'Lens': '镜头',
  'Captured at': '拍摄时间',

  'Close': '关闭',
  'Loading': '加载中',
  'No content': '无可用内容',
  'Load failed': '加载失败',
};

const i18n = window.__FOXEL_EXTERNALS__.i18n!;
export const { t, useI18n } = i18n.create({ zh });
