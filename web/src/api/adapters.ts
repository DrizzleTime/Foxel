import request from './client';

export interface AdapterItem {
  id: number;
  name: string;
  type: string;
  config: any;
  enabled: boolean;
  path?: string | null;
  sub_path?: string | null;
}

export interface AdapterTypeField {
  key: string;
  label: string;
  type: 'string' | 'password' | 'number' | 'boolean';
  required?: boolean;
  placeholder?: string;
  default?: any;
}

export interface AdapterTypeMeta {
  type: string;
  name: string;
  config_schema: AdapterTypeField[];
}

export const adaptersApi = {
  list: () => request<AdapterItem[]>('/adapters'),
  create: (payload: Omit<AdapterItem, 'id'>) => request<AdapterItem>('/adapters', { method: 'POST', json: payload }),
  update: (id: number, payload: Omit<AdapterItem, 'id'>) => request<AdapterItem>(`/adapters/${id}`, { method: 'PUT', json: payload }),
  remove: (id: number) => request<void>(`/adapters/${id}`, { method: 'DELETE' }),
  available: () => request<AdapterTypeMeta[]>('/adapters/available'),
};
