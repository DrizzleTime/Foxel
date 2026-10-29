export const PLUGIN_PROTOCOL_VERSION = 1;
export type HostMethod = 'close' | 'openPath' | 'openFile';
export interface HostRequest {
  type: 'foxel-plugin:request';
  protocol: typeof PLUGIN_PROTOCOL_VERSION;
  pluginKey: string;
  id: string;
  method: HostMethod;
  params: Record<string, unknown>;
}
export interface HostResult {
  type: 'foxel-plugin:result';
  protocol: typeof PLUGIN_PROTOCOL_VERSION;
  pluginKey: string;
  id: string;
  error?: string;
}
export function isHostRequest(value: unknown): value is HostRequest {
  if (!value || typeof value !== 'object') return false;
  const data = value as Partial<HostRequest>;
  return data.type === 'foxel-plugin:request' && data.protocol === PLUGIN_PROTOCOL_VERSION
    && typeof data.id === 'string' && data.id.length > 0 && data.id.length < 128
    && typeof data.pluginKey === 'string'
    && ['close', 'openPath', 'openFile'].includes(data.method || '')
    && !!data.params && typeof data.params === 'object' && !Array.isArray(data.params);
}
// eslint-disable-next-line no-control-regex -- VFS paths must reject control characters and backslashes.
const INVALID_PATH_CHARACTERS = /[\x00-\x1f\\]/;

export function requireVfsPath(value: unknown): string {
  if (typeof value !== 'string' || !value.startsWith('/') || value.length > 8192
    || INVALID_PATH_CHARACTERS.test(value) || value.split('/').includes('..')) {
    throw new Error('Invalid VFS path');
  }
  return value.replace(/\/+$/, '') || '/';
}
