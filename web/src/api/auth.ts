import request from './client';

export interface LoginPayload {
  username: string;
  password: string;
}

export interface RegisterPayload {
  username: string;
  password: string;
  email?: string;
  full_name?: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface MeResponse {
  id: number;
  username: string;
  email?: string | null;
  full_name?: string | null;
  gravatar_url: string;
}

export interface UpdateMePayload {
  email?: string | null;
  full_name?: string | null;
  old_password?: string;
  new_password?: string;
}

export interface PasswordResetRequestPayload {
  email: string;
}

export interface PasswordResetConfirmPayload {
  token: string;
  password: string;
}

export const authApi = {
  register: async (username: string, password: string, email?: string, full_name?: string): Promise<any> => {
    return request('/auth/register', {
      method: 'POST',
      json: { username, password, email, full_name },
    });
  },
  login: async (payload: LoginPayload) => {
    const form = new URLSearchParams();
    form.append('username', payload.username);
    form.append('password', payload.password);
    try {
      return await request<AuthResponse>('/auth/login', {
        method: 'POST',
        body: form,
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
      });
    } catch (e) {
      console.error('[authApi.login] error:', e);
      throw e;
    }
  },
  logout: () => {
    localStorage.removeItem('token');
  },
  me: async () => {
    return await request<MeResponse>('/auth/me', {
      method: 'GET',
    });
  },
  updateMe: async (payload: UpdateMePayload) => {
    return await request<MeResponse>('/auth/me', {
      method: 'PUT',
      json: payload,
    });
  },
  requestPasswordReset: async (payload: PasswordResetRequestPayload) => {
    return await request('/auth/password-reset/request', {
      method: 'POST',
      json: payload,
    });
  },
  verifyPasswordResetToken: async (token: string) => {
    return await request<{ username: string; email: string }>('/auth/password-reset/verify?token=' + encodeURIComponent(token));
  },
  confirmPasswordReset: async (payload: PasswordResetConfirmPayload) => {
    return await request('/auth/password-reset/confirm', {
      method: 'POST',
      json: payload,
    });
  },
};
