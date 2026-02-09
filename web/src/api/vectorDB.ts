import client from './client';

export interface VectorDBIndexInfo {
  index_name: string;
  index_type?: string;
  metric_type?: string;
  indexed_rows: number;
  pending_index_rows: number;
  state?: string;
}

export interface VectorDBCollectionStats {
  name: string;
  row_count: number;
  dimension: number | null;
  estimated_memory_bytes: number;
  is_vector_collection: boolean;
  indexes: VectorDBIndexInfo[];
}

export interface VectorDBStats {
  collections: VectorDBCollectionStats[];
  collection_count: number;
  total_vectors: number;
  estimated_total_memory_bytes: number;
  db_file_size_bytes: number | null;
}

export interface VectorDBProviderField {
  key: string;
  label: string;
  type: 'text' | 'password';
  required?: boolean;
  default?: string;
  placeholder?: string;
}

export interface VectorDBProviderMeta {
  type: string;
  label: string;
  description?: string;
  enabled: boolean;
  config_schema: VectorDBProviderField[];
}

export interface VectorDBCurrentConfig {
  type: string;
  config: Record<string, string>;
  label?: string;
  enabled?: boolean;
}

export interface UpdateVectorDBConfigResponse {
  config: VectorDBCurrentConfig;
  stats: VectorDBStats;
}

export const vectorDBApi = {
  getProviders: () => client<VectorDBProviderMeta[]>('/vector-db/providers', { method: 'GET' }),
  getConfig: () => client<VectorDBCurrentConfig>('/vector-db/config', { method: 'GET' }),
  getStats: () => client<VectorDBStats>('/vector-db/stats', { method: 'GET' }),
  updateConfig: (payload: { type: string; config: Record<string, string> }) =>
    client<UpdateVectorDBConfigResponse>('/vector-db/config', { method: 'POST', json: payload }),
  clearAll: () => client('/vector-db/clear-all', { method: 'POST' }),
};
