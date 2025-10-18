import request from './client';

export type AIAbility = 'chat' | 'vision' | 'embedding' | 'rerank' | 'voice' | 'tools';

export interface AIProviderPayload {
  name: string;
  identifier: string;
  provider_type?: string | null;
  api_format: 'openai' | 'gemini';
  base_url?: string | null;
  api_key?: string | null;
  logo_url?: string | null;
  extra_config?: Record<string, unknown> | null;
}

export interface AIProvider extends Omit<AIProviderPayload, 'extra_config'> {
  id: number;
  extra_config: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  models?: AIModel[];
}

export interface AIModelPayload {
  name: string;
  display_name?: string | null;
  description?: string | null;
  capabilities?: AIAbility[];
  context_window?: number | null;
  embedding_dimensions?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface AIModel extends Omit<AIModelPayload, 'metadata'> {
  id: number;
  provider_id: number;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  provider?: AIProvider;
}

export type AIDefaultAssignments = Partial<Record<AIAbility, number | null>>;
export type AIDefaultModels = Partial<Record<AIAbility, AIModel | null>>;

export async function fetchProviders() {
  const data = await request<{ providers: AIProvider[] }>('/ai/providers');
  return data.providers;
}

export async function createProvider(payload: AIProviderPayload) {
  return request<AIProvider>('/ai/providers', { method: 'POST', json: payload });
}

export async function updateProvider(id: number, payload: Partial<AIProviderPayload>) {
  return request<AIProvider>(`/ai/providers/${id}`, { method: 'PUT', json: payload });
}

export async function deleteProvider(id: number) {
  await request(`/ai/providers/${id}`, { method: 'DELETE' });
}

export async function syncProviderModels(id: number) {
  return request<{ created: number; updated: number }>(`/ai/providers/${id}/sync-models`, { method: 'POST' });
}

export async function fetchRemoteModels(providerId: number) {
  return request<{ models: AIModelPayload[] }>(`/ai/providers/${providerId}/remote-models`);
}

export async function createModel(providerId: number, payload: AIModelPayload) {
  return request<AIModel>(`/ai/providers/${providerId}/models`, { method: 'POST', json: payload });
}

export async function updateModel(modelId: number, payload: Partial<AIModelPayload>) {
  return request<AIModel>(`/ai/models/${modelId}`, { method: 'PUT', json: payload });
}

export async function deleteModel(modelId: number) {
  await request(`/ai/models/${modelId}`, { method: 'DELETE' });
}

export async function fetchDefaults() {
  return request<AIDefaultModels>('/ai/defaults');
}

export async function updateDefaults(payload: AIDefaultAssignments) {
  return request<AIDefaultModels>('/ai/defaults', { method: 'PUT', json: payload });
}
