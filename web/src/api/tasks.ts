import request from './client';
import type { TaskProgress } from './offlineDownloads';

export interface AutomationTask {
  id: number;
  name: string;
  event: string;
  trigger_config?: Record<string, any>;
  processor_type: string;
  processor_config: Record<string, any>;
  enabled: boolean;
}

export type AutomationTaskCreate = Omit<AutomationTask, 'id'>;
export type AutomationTaskUpdate = Partial<AutomationTaskCreate>;

export interface QueuedTask {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'success' | 'failed';
  result?: any;
  error?: string;
  task_info: Record<string, any>;
  progress?: TaskProgress | null;
  meta?: Record<string, any> | null;
}

export interface TaskQueueSettings {
  concurrency: number;
  active_workers: number;
}

export interface TaskQueueSettingsUpdate {
  concurrency: number;
}

export const tasksApi = {
  list: () => request<AutomationTask[]>('/tasks/'),
  create: (payload: AutomationTaskCreate) => request<AutomationTask>('/tasks/', { method: 'POST', json: payload }),
  update: (id: number, payload: AutomationTaskUpdate) => request<AutomationTask>(`/tasks/${id}`, { method: 'PUT', json: payload }),
  remove: (id: number) => request<void>(`/tasks/${id}`, { method: 'DELETE' }),
  getQueue: () => request<QueuedTask[]>('/tasks/queue'),
  getQueueSettings: () => request<TaskQueueSettings>('/tasks/queue/settings'),
  updateQueueSettings: (payload: TaskQueueSettingsUpdate) => request<TaskQueueSettings>('/tasks/queue/settings', { method: 'POST', json: payload }),
};
