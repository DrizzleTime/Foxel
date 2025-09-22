export interface RequestOptions extends RequestInit {
  json?: any;
  formData?: FormData;
  text?: string;
  rawResponse?: boolean;
}
const BASE_URL = import.meta.env.PROD ? '/api' : 'http://127.0.0.1:8000/api';
export const API_BASE_URL = BASE_URL;

async function request<T = any>(url: string, options: RequestOptions = {}): Promise<T> {
  const { json, formData, text, rawResponse, headers, ...rest } = options;
  const finalHeaders: Record<string, string> = {
    ...(headers as Record<string, string> || {})
  };

  const token = localStorage.getItem('token');
  if (token) {
    finalHeaders['Authorization'] = `Bearer ${token}`;
  }

  let body: BodyInit | undefined;
  if (json !== undefined) {
    body = JSON.stringify(json);
    finalHeaders['Content-Type'] = 'application/json';
  } else if (formData) {
    body = formData; 
  } else if (text !== undefined) {
    body = text;
    finalHeaders['Content-Type'] = 'text/plain;charset=utf-8';
  } else if ((rest as any).body !== undefined) {
    body = (rest as any).body;
    delete (rest as any).body;
  }

  const resp = await fetch(BASE_URL + url, {
    ...rest,
    headers: finalHeaders,
    body,
  });

  if (rawResponse) return resp as any;

  if (!resp.ok) {
    let errMsg = resp.statusText;
    try {
      const data = await resp.json();
      if (Array.isArray(data?.detail)) {
        errMsg = data.detail.map((e: any) => e.msg || JSON.stringify(e)).join('; ');
      } else {
        errMsg = (typeof data?.detail === 'string') ? data.detail : (data.detail ? JSON.stringify(data.detail) : JSON.stringify(data));
      }
    } catch (_) { }
    throw new Error(errMsg || `Request failed: ${resp.status}`);
  }

  const contentType = resp.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    const json = await resp.json();
    if (json && typeof json === 'object' && 'code' in json && ('msg' in json || 'message' in json)) {
      if (json.code !== 0) {
        throw new Error(json.msg || json.message || 'Error');
      }
      return json.data as T;
    }
    return json;
  }
  if (contentType.startsWith('text/')) {
    return await resp.text() as any;
  }
  return await resp.arrayBuffer() as any;
}

export { vfsApi, type VfsEntry, type DirListing } from './vfs';
export { adaptersApi, type AdapterItem, type AdapterTypeField, type AdapterTypeMeta } from './adapters';
export { shareApi, type ShareInfo, type ShareInfoWithPassword } from './share';
export { offlineDownloadsApi, type OfflineDownloadTask, type OfflineDownloadCreate, type TaskProgress } from './offlineDownloads';
export default request;
