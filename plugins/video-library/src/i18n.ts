type Dict = Record<string, string>;

const zh: Dict = {
  'Request failed': '请求失败',
  'Load failed': '加载失败',
  'Video Library': '视频库',
  'Total: {total} · Movies: {movies} · TV Shows: {tvShows}': '总计: {total} · 电影: {movies} · 电视剧: {tvShows}',
  'All': '全部',
  'Movies': '电影',
  'TV Shows': '电视剧',
  'Search': '搜索',
  'Refresh': '刷新',
  'No data': '暂无数据',
  '{count} episodes': '{count} 集',
  'Details': '详情',
  'No overview': '暂无简介',
  'Movie': '电影',
  'TV': '电视剧',
};

const i18n = window.__FOXEL_EXTERNALS__.i18n!;
export const { t, useI18n } = i18n.create({ zh });
