import request from './client';

export interface PluginItem {
  id: number;
  key: string;
  open_app?: boolean | null;
  name?: string | null;
  version?: string | null;
  supported_exts?: string[] | null;
  default_bounds?: Record<string, number> | null;
  default_maximized?: boolean | null;
  icon?: string | null;
  description?: string | null;
  author?: string | null;
  website?: string | null;
  github?: string | null;
  license?: string | null;
  manifest?: Record<string, unknown> | null;
  loaded_routes?: string[] | null;
  loaded_processors?: string[] | null;
}

export interface PluginInstallResult {
  success: boolean;
  plugin?: PluginItem;
  message?: string;
  errors?: string[];
}

export const pluginsApi = {
  /**
   * 获取已安装插件列表
   */
  list: () => request<PluginItem[]>(`/plugins`),

  /**
   * 获取单个插件详情
   */
  get: (key: string) => request<PluginItem>(`/plugins/${key}`),

  /**
   * 安装插件（上传 .foxpkg）
   */
  install: async (file: File): Promise<PluginInstallResult> => {
    const formData = new FormData();
    formData.append('file', file);
    return request<PluginInstallResult>(`/plugins/install`, {
      method: 'POST',
      formData,
    });
  },

  /**
   * 删除/卸载插件
   */
  remove: (key: string) => request(`/plugins/${key}`, { method: 'DELETE' }),

  /**
   * 获取插件 bundle URL
   */
  getBundleUrl: (key: string) => `/api/plugins/${key}/bundle.js`,

  /**
   * 获取插件资源 URL
   */
  getAssetUrl: (key: string, assetPath: string) =>
    `/api/plugins/${key}/assets/${assetPath}`,
};
