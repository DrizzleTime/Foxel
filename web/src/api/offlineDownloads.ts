import request from './client';

export interface TaskProgress {
  stage?: string | null;
  percent?: number | null;
  bytes_total?: number | null;
  bytes_done?: number | null;
  detail?: string | null;
}

export interface OfflineDownloadTask {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  result?: any;
  error?: string | null;
  task_info: Record<string, any>;
  progress?: TaskProgress | null;
  meta?: Record<string, any> | null;
}

export interface OfflineDownloadCreate {
  url: string;
  dest_dir: string;
  filename: string;
}

export const offlineDownloadsApi = {
  create: (payload: OfflineDownloadCreate) => request<{ task_id: string }>('/offline-downloads/', {
    method: 'POST',
    json: payload,
  }),
  list: () => request<OfflineDownloadTask[]>('/offline-downloads/'),
  detail: (taskId: string) => request<OfflineDownloadTask>(`/offline-downloads/${taskId}`),
};
