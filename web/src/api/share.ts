import request, { API_BASE_URL } from './client';
import type { DirListing } from './vfs';

export interface ShareInfo {
  id: number;
  token: string;
  name: string;
  paths: string[];
  created_at: string;
  expires_at?: string;
  access_type: 'public' | 'password';
}

export interface ShareInfoWithPassword extends ShareInfo {
  password?: string;
}

export interface ShareCreatePayload {
  name: string;
  paths: string[];
  expires_in_days?: number;
  access_type: 'public' | 'password';
  password?: string;
}

export interface ClearExpiredResult {
  deleted_count: number;
}

export const shareApi = {
  create: (payload: ShareCreatePayload) => request<ShareInfoWithPassword>('/shares', { method: 'POST', json: payload }),
  list: () => request<ShareInfo[]>('/shares'),
  remove: (shareId: number) => request<void>(`/shares/${shareId}`, { method: 'DELETE' }),
  clearExpired: () => request<ClearExpiredResult>(`/shares/expired`, { method: 'DELETE' }),
  get: (token: string) => request<ShareInfo>(`/s/${token}`),
  verifyPassword: (token: string, password: string) => request<void>(`/s/${token}/verify`, { method: 'POST', json: { password } }),
  listDir: (token: string, path: string = '/', password?: string) => {
    const params: Record<string, string> = { path };
    if (password) {
      params.password = password;
    }
    return request<DirListing>(`/s/${token}/ls?${new URLSearchParams(params)}`);
  },
  downloadUrl: (token: string, path: string, password?: string) => {
    const url = `${API_BASE_URL}/s/${token}/download?path=${encodeURIComponent(path)}`;
    return password ? `${url}&password=${encodeURIComponent(password)}` : url;
  },
};
