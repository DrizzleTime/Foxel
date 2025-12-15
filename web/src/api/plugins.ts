import request from './client';

export interface PluginItem {
  id: number;
  url: string;
  enabled: boolean;
  open_app?: boolean | null;
  key?: string | null;
  name?: string | null;
  version?: string | null;
  supported_exts?: string[] | null;
  default_bounds?: Record<string, any> | null;
  default_maximized?: boolean | null;
  icon?: string | null;
  description?: string | null;
  author?: string | null;
  website?: string | null;
  github?: string | null;
}

export interface PluginCreate {
  url: string;
  enabled?: boolean;
}

export interface PluginManifestUpdate {
  key?: string;
  name?: string;
  version?: string;
  open_app?: boolean;
  supported_exts?: string[];
  default_bounds?: Record<string, any>;
  default_maximized?: boolean;
  icon?: string;
  description?: string;
  author?: string;
  website?: string;
  github?: string;
}

export const pluginsApi = {
  list: () => request<PluginItem[]>(`/plugins`),
  create: (payload: PluginCreate) => request<PluginItem>(`/plugins`, { method: 'POST', json: payload }),
  remove: (id: number) => request(`/plugins/${id}`, { method: 'DELETE' }),
  update: (id: number, payload: PluginCreate) => request<PluginItem>(`/plugins/${id}`, { method: 'PUT', json: payload }),
  updateManifest: (id: number, payload: PluginManifestUpdate) => request<PluginItem>(`/plugins/${id}/metadata`, { method: 'POST', json: payload }),
};
