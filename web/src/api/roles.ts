import request from './client';
import type { UserInfo } from './users';

export interface RoleInfo {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  created_at: string;
}

export interface RoleDetail extends RoleInfo {
  permissions: string[];
  path_rules_count: number;
}

export interface RoleCreate {
  name: string;
  description?: string | null;
}

export interface RoleUpdate {
  name?: string | null;
  description?: string | null;
}

export interface PathRuleInfo {
  id: number;
  role_id: number;
  path_pattern: string;
  is_regex: boolean;
  can_read: boolean;
  can_write: boolean;
  can_delete: boolean;
  can_share: boolean;
  priority: number;
  created_at: string;
}

export interface PathRuleCreate {
  path_pattern: string;
  is_regex?: boolean;
  can_read?: boolean;
  can_write?: boolean;
  can_delete?: boolean;
  can_share?: boolean;
  priority?: number;
}

export const rolesApi = {
  list: async (): Promise<RoleInfo[]> => {
    return await request<RoleInfo[]>('/roles');
  },

  get: async (roleId: number): Promise<RoleDetail> => {
    return await request<RoleDetail>(`/roles/${roleId}`);
  },

  getUsers: async (roleId: number): Promise<UserInfo[]> => {
    return await request<UserInfo[]>(`/roles/${roleId}/users`);
  },

  create: async (data: RoleCreate): Promise<RoleInfo> => {
    return await request<RoleInfo>('/roles', {
      method: 'POST',
      json: data,
    });
  },

  update: async (roleId: number, data: RoleUpdate): Promise<RoleInfo> => {
    return await request<RoleInfo>(`/roles/${roleId}`, {
      method: 'PUT',
      json: data,
    });
  },

  remove: async (roleId: number): Promise<void> => {
    await request(`/roles/${roleId}`, { method: 'DELETE' });
  },

  setPermissions: async (roleId: number, permissionCodes: string[]): Promise<string[]> => {
    return await request<string[]>(`/roles/${roleId}/permissions`, {
      method: 'POST',
      json: { permission_codes: permissionCodes },
    });
  },

  getPathRules: async (roleId: number): Promise<PathRuleInfo[]> => {
    return await request<PathRuleInfo[]>(`/roles/${roleId}/path-rules`);
  },

  addPathRule: async (roleId: number, data: PathRuleCreate): Promise<PathRuleInfo> => {
    return await request<PathRuleInfo>(`/roles/${roleId}/path-rules`, {
      method: 'POST',
      json: data,
    });
  },

  updatePathRule: async (ruleId: number, data: PathRuleCreate): Promise<PathRuleInfo> => {
    return await request<PathRuleInfo>(`/path-rules/${ruleId}`, {
      method: 'PUT',
      json: data,
    });
  },

  deletePathRule: async (ruleId: number): Promise<void> => {
    await request(`/path-rules/${ruleId}`, { method: 'DELETE' });
  },
};
