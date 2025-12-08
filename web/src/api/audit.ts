import request from './client';

export interface AuditLogItem {
  id: number;
  created_at: string;
  action: string;
  description?: string | null;
  user_id?: number | null;
  username?: string | null;
  client_ip?: string | null;
  method: string;
  path: string;
  status_code: number;
  duration_ms?: number | null;
  success: boolean;
  request_params?: Record<string, any> | null;
  request_body?: Record<string, any> | null;
  error?: string | null;
}

export interface PaginatedAuditLogs {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface GetAuditLogsParams {
  page?: number;
  page_size?: number;
  action?: string;
  success?: boolean;
  username?: string;
  path?: string;
  start_time?: string;
  end_time?: string;
}

export interface ClearAuditLogsParams {
  start_time?: string;
  end_time?: string;
}

export const auditApi = {
  list: (params: GetAuditLogsParams = {}) => {
    const query = new URLSearchParams();
    if (params.page) query.append('page', params.page.toString());
    if (params.page_size) query.append('page_size', params.page_size.toString());
    if (params.action) query.append('action', params.action);
    if (params.success !== undefined && params.success !== null) query.append('success', String(params.success));
    if (params.username) query.append('username', params.username);
    if (params.path) query.append('path', params.path);
    if (params.start_time) query.append('start_time', params.start_time);
    if (params.end_time) query.append('end_time', params.end_time);
    const qs = query.toString();
    return request<PaginatedAuditLogs>(`/audit/logs${qs ? `?${qs}` : ''}`);
  },
  clear: (params: ClearAuditLogsParams = {}) => {
    const query = new URLSearchParams();
    if (params.start_time) query.append('start_time', params.start_time);
    if (params.end_time) query.append('end_time', params.end_time);
    const qs = query.toString();
    return request<{ deleted_count: number }>(`/audit/logs${qs ? `?${qs}` : ''}`, {
      method: 'DELETE',
    });
  },
};
