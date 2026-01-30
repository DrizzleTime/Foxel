import request from './client';

export interface UserInfo {
  id: number;
  username: string;
  email: string | null;
  full_name: string | null;
  disabled: boolean;
  is_admin: boolean;
  created_at: string;
  last_login: string | null;
}

export interface UserDetail extends UserInfo {
  roles: string[];
  created_by_username: string | null;
}

export interface UserCreate {
  username: string;
  password: string;
  email?: string | null;
  full_name?: string | null;
  is_admin?: boolean;
  disabled?: boolean;
  role_ids?: number[];
}

export interface UserUpdate {
  email?: string | null;
  full_name?: string | null;
  password?: string | null;
  is_admin?: boolean | null;
  disabled?: boolean | null;
}

export const usersApi = {
  list: async (): Promise<UserInfo[]> => {
    return await request<UserInfo[]>('/users');
  },

  get: async (userId: number): Promise<UserDetail> => {
    return await request<UserDetail>(`/users/${userId}`);
  },

  create: async (data: UserCreate): Promise<UserDetail> => {
    return await request<UserDetail>('/users', {
      method: 'POST',
      json: data,
    });
  },

  update: async (userId: number, data: UserUpdate): Promise<UserDetail> => {
    return await request<UserDetail>(`/users/${userId}`, {
      method: 'PUT',
      json: data,
    });
  },

  remove: async (userId: number): Promise<void> => {
    await request(`/users/${userId}`, { method: 'DELETE' });
  },

  setRoles: async (userId: number, roleIds: number[]): Promise<string[]> => {
    return await request<string[]>(`/users/${userId}/roles`, {
      method: 'POST',
      json: { role_ids: roleIds },
    });
  },

  removeRole: async (userId: number, roleId: number): Promise<string[]> => {
    return await request<string[]>(`/users/${userId}/roles/${roleId}`, {
      method: 'DELETE',
    });
  },
};

