import request from './client';
import type { PathRuleInfo } from './roles';

export interface PermissionInfo {
  id: number;
  code: string;
  name: string;
  category: string;
  description: string | null;
}

export interface UserPermissions {
  user_id: number;
  is_admin: boolean;
  permissions: string[];
  path_rules: PathRuleInfo[];
}

export const permissionsApi = {
  listAll: async (): Promise<PermissionInfo[]> => {
    return await request<PermissionInfo[]>('/permissions');
  },

  getMine: async (): Promise<UserPermissions> => {
    return await request<UserPermissions>('/me/permissions');
  },
};
