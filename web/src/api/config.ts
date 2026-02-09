import request from './client';

export async function getConfig(key: string) {
  return request<{ key: string; value: string }>('/config/?key=' + encodeURIComponent(key));
}

export async function setConfig(key: string, value?: string | null) {
  const form = new FormData();
  form.append('key', key);
  form.append('value', value ?? '');
  return request('/config/', { method: 'POST', formData: form });
}

export async function getAllConfig() {
  return request<Record<string, string>>('/config/all');
}

export async function getPublicConfig() {
  return request<Record<string, string>>('/config/public');
}

export interface SystemStatus {
  version: string;
  title: string;
  logo: string;
  favicon: string;
  is_initialized: boolean;
  app_domain?: string;
  file_domain?: string;
}

export async function status() {
  return request<SystemStatus>('/config/status');
}

export async function getLatestVersion() {
  return request<{ latest_version: string | null, body: string | null }>('/config/latest-version');
}
