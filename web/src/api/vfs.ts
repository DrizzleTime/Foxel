import request, { API_BASE_URL } from './client';
import { encodeFilePath, retryTransfer, runTransferWorkers, sendUpload, transferJson,
  TRANSFER_CHUNK_SIZE } from './transfers';

export interface UploadTransferState {
  session?: { upload_id: string; chunk_size: number; parts: number };
}

export interface VfsEntry {
  name: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  type?: string; 
  has_thumbnail?: boolean;
}

export interface DirListing {
  path: string;
  entries: VfsEntry[];
  pagination?: {
    mode?: 'paged' | 'cursor';
    page_size: number;
    total?: number;
    page?: number;
    pages?: number;
    cursor?: string | null;
    next_cursor?: string | null;
    has_next?: boolean;
  };
}

export interface SearchResultItem {
  id: string;
  path: string;
  score: number;
  chunk_id?: string;
  snippet?: string;
  mime?: string;
  source_type?: string;
  start_offset?: number;
  end_offset?: number;
  metadata?: Record<string, any>;
}

export interface SearchPagination {
  page: number;
  page_size: number;
  has_more: boolean;
}

export interface SearchResponse {
  items: SearchResultItem[];
  query: string;
  mode?: string;
  pagination?: SearchPagination;
}

export const vfsApi = {
  abortUploadSession: (id: string) => request(`/fs/uploads/${id}`, { method: 'DELETE' }),
  uploadOptimized: async (fullPath: string, file: File, overwrite = true,
    onProgress?: (loaded: number, total: number) => void, signal?: AbortSignal,
    state: UploadTransferState = {}) => {
    if (file.size <= TRANSFER_CHUNK_SIZE) {
      return sendUpload(`${API_BASE_URL}/fs/upload-raw/${encodeFilePath(fullPath)}?overwrite=${overwrite}`,
        file, onProgress, signal);
    }
    const base = `${API_BASE_URL}/fs/uploads`;
    let uploaded: number[] = [];
    if (state.session) {
      try {
        const status = await transferJson<{ uploaded: number[]; completed: boolean }>(`${base}/${state.session.upload_id}`, { signal });
        if (status.completed) {
          const result = await transferJson<{ path: string; size: number }>(`${base}/${state.session.upload_id}/complete`, { method: 'POST', signal });
          state.session = undefined;
          return result;
        }
        uploaded = status.uploaded;
      } catch (error) {
        const status = (error as { status?: number }).status;
        if (status !== 404 && status !== 410) throw error;
        state.session = undefined;
      }
    }
    if (!state.session) {
      state.session = await transferJson(`${base}`, {
        method: 'POST', body: JSON.stringify({ path: fullPath, size: file.size, overwrite }), signal,
      });
    }
    const session = state.session!;
    const done = new Set(uploaded);
    const progress = Array.from({ length: session.parts }, (_, index) => done.has(index)
      ? Math.min(session.chunk_size, file.size - index * session.chunk_size) : 0);
    const report = () => onProgress?.(progress.reduce((sum, bytes) => sum + bytes, 0), file.size);
    report();
    await runTransferWorkers(session.parts, 4, async (index, workerSignal) => {
      if (done.has(index)) return;
      const start = index * session.chunk_size;
      const chunk = file.slice(start, Math.min(file.size, start + session.chunk_size));
      await retryTransfer(() => {
        progress[index] = 0;
        report();
        return sendUpload(`${base}/${session.upload_id}/parts/${index}`, chunk, loaded => {
          progress[index] = Math.min(loaded, chunk.size);
          report();
        }, workerSignal);
      }, workerSignal);
      progress[index] = chunk.size;
      report();
    }, signal);
    const result = await retryTransfer(() => transferJson<{ path: string; size: number }>(
      `${base}/${session.upload_id}/complete?overwrite=${overwrite}`, { method: 'POST', signal }), signal);
    state.session = undefined;
    return result;
  },
  list: (path: string, page: number = 1, pageSize: number = 50, sortBy: string = 'name', sortOrder: string = 'asc', cursor?: string | null) => {
    const cleaned = path.replace(/\\/g, '/');
    const trimmed = cleaned === '/' ? '' : cleaned.replace(/^\/+/, '');
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
      sort_by: sortBy,
      sort_order: sortOrder
    });
    if (cursor) params.set('cursor', cursor);
    return request<DirListing>(`/fs/${encodeURI(trimmed)}?${params}`);
  },
  readFile: async (path: string) => {
    const enc = encodeFilePath(path);
    const resp = await request(`/fs/file/${enc}`, { rawResponse: true });
    return await (resp as Response).arrayBuffer();
  },
  uploadFile: (fullPath: string, file: File | Blob) => {
    const fd = new FormData();
    fd.append('file', file);
    return request(`/fs/file/${encodeURI(fullPath.replace(/^\/+/, ''))}`, { method: 'POST', formData: fd });
  },
  mkdir: (path: string) => request('/fs/mkdir', { method: 'POST', json: { path } }),
  deletePath: (path: string) => request(`/fs/${encodeURI(path.replace(/^\/+/, ''))}`, { method: 'DELETE' }),
  move: (src: string, dst: string, options?: { overwrite?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.overwrite !== undefined) params.set('overwrite', String(options.overwrite));
    const query = params.toString();
    return request(`/fs/move${query ? `?${query}` : ''}`, { method: 'POST', json: { src, dst } });
  },
  copy: (src: string, dst: string, options?: { overwrite?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.overwrite !== undefined) params.set('overwrite', String(options.overwrite));
    const query = params.toString();
    return request(`/fs/copy${query ? `?${query}` : ''}`, { method: 'POST', json: { src, dst } });
  },
  rename: (src: string, dst: string) => request('/fs/rename', { method: 'POST', json: { src, dst } }),
  thumb: (path: string, w=256, h=256, fit='cover') =>
    request<ArrayBuffer>(`/fs/thumb/${encodeURI(path.replace(/^\/+/, ''))}?w=${w}&h=${h}&fit=${fit}`),
  streamUrl: (path: string) => `${API_BASE_URL}/fs/stream/${encodeURI(path.replace(/^\/+/, ''))}`,
  stat: (path: string, options?: { verbose?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.verbose) params.set('verbose', 'true');
    const query = params.toString();
    return request(`/fs/stat/${encodeFilePath(path)}${query ? `?${query}` : ''}`);
  },
  getTempLinkToken: (path: string, expiresIn: number = 3600) =>
    request<{token: string, path: string, url: string}>(`/fs/temp-link/${encodeFilePath(path)}?expires_in=${expiresIn}`),
  getTempPublicUrl: (token: string) => `${API_BASE_URL}/fs/public/${token}`,
  uploadRaw: (fullPath: string, file: File, overwrite: boolean = true, onProgress?: (loaded: number, total: number) => void) => {
    const enc = encodeURI(fullPath.replace(/^\/+/, ''));
    return new Promise<any>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('PUT', `${API_BASE_URL}/fs/upload-raw/${enc}?overwrite=${overwrite}`);
      const token = localStorage.getItem('token');
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable && onProgress) onProgress(ev.loaded, ev.total);
      };
      xhr.onreadystatechange = () => {
        if (xhr.readyState === 4) {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const json = JSON.parse(xhr.responseText);
              if (json.code === 0) return resolve(json.data);
              return reject(new Error(json.msg || json.message || 'Upload failed'));
            } catch {
              return reject(new Error('Invalid response'));
            }
          } else {
            let err = 'Upload failed';
            try {
              const json = JSON.parse(xhr.responseText);
              err = json.detail || json.msg || json.message || err;
            } catch { void 0; }
            reject(new Error(err));
          }
        }
      };
      xhr.send(file);
    });
  },
  uploadStream: (fullPath: string, file: File, overwrite: boolean = true, onProgress?: (loaded: number, total: number) => void) => {
    const enc = encodeURI(fullPath.replace(/^\/+/, ''));
    return new Promise<any>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE_URL}/fs/upload/${enc}?overwrite=${overwrite}`);
      const token = localStorage.getItem('token');
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable && onProgress) onProgress(ev.loaded, ev.total);
      };
      xhr.onreadystatechange = () => {
        if (xhr.readyState === 4) {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const json = JSON.parse(xhr.responseText);
              if (json.code === 0) return resolve(json.data);
              return reject(new Error(json.msg || json.message || 'Upload failed'));
            } catch {
              return reject(new Error('Invalid response'));
            }
          } else {
            let err = 'Upload failed';
            try {
              const json = JSON.parse(xhr.responseText);
              err = json.detail || json.msg || json.message || err;
            } catch { void 0; }
            reject(new Error(err));
          }
        }
      };
      const fd = new FormData();
      fd.append('file', file);
      xhr.send(fd);
    });
  },
  searchFiles: (
    q: string,
    top_k: number = 10,
    mode: 'vector' | 'filename' = 'vector',
    page?: number,
    page_size?: number,
  ) => {
    const params = new URLSearchParams({
      q,
      top_k: String(top_k),
      mode,
    });
    if (page !== undefined) params.set('page', String(page));
    if (page_size !== undefined) params.set('page_size', String(page_size));
    return request<SearchResponse>(`/fs/search?${params.toString()}`);
  },
};
