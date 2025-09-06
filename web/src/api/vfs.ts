import request, { API_BASE_URL } from './client';

export interface VfsEntry {
  name: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  type?: string; 
  is_image?: boolean;
}

export interface DirListing {
  path: string;
  entries: VfsEntry[];
  pagination?: {
    total: number;
    page: number;
    page_size: number;
    pages: number;
  };
}

export interface SearchResultItem {
  id: number;
  path: string;
  score: number;
}

export const vfsApi = {
  list: (path: string, page: number = 1, pageSize: number = 50, sortBy: string = 'name', sortOrder: string = 'asc') => {
    const cleaned = path.replace(/\\/g, '/');
    const trimmed = cleaned === '/' ? '' : cleaned.replace(/^\/+/, '');
    const params = new URLSearchParams({
      page: page.toString(),
      page_size: pageSize.toString(),
      sort_by: sortBy,
      sort_order: sortOrder
    });
    return request<DirListing>(`/fs/${encodeURI(trimmed)}?${params}`);
  },
  readFile: (path: string) => request<ArrayBuffer>(`/fs/file/${encodeURI(path.replace(/^\/+/, ''))}`),
  uploadFile: (fullPath: string, file: File | Blob) => {
    const fd = new FormData();
    fd.append('file', file);
    return request(`/fs/file/${encodeURI(fullPath.replace(/^\/+/, ''))}`, { method: 'POST', formData: fd });
  },
  mkdir: (path: string) => request('/fs/mkdir', { method: 'POST', json: { path } }),
  deletePath: (path: string) => request(`/fs/${encodeURI(path.replace(/^\/+/, ''))}`, { method: 'DELETE' }),
  move: (src: string, dst: string) => request('/fs/move', { method: 'POST', json: { src, dst } }),
  rename: (src: string, dst: string) => request('/fs/rename', { method: 'POST', json: { src, dst } }),
  thumb: (path: string, w=256, h=256, fit='cover') =>
    request<ArrayBuffer>(`/fs/thumb/${encodeURI(path.replace(/^\/+/, ''))}?w=${w}&h=${h}&fit=${fit}`),
  streamUrl: (path: string) => `${API_BASE_URL}/fs/stream/${encodeURI(path.replace(/^\/+/, ''))}`,
  stat: (path: string) => request(`/fs/stat/${encodeURI(path.replace(/^\/+/, ''))}`),
  getTempLinkToken: (path: string, expiresIn: number = 3600) =>
    request<{token: string, path: string, url: string}>(`/fs/temp-link/${encodeURI(path.replace(/^\/+/, ''))}?expires_in=${expiresIn}`),
  getTempPublicUrl: (token: string) => `${API_BASE_URL}/fs/public/${token}`,
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
            } catch (e) {
              return reject(new Error('Invalid response'));
            }
          } else {
            let err = 'Upload failed';
            try {
              const json = JSON.parse(xhr.responseText);
              err = json.detail || json.msg || json.message || err;
            } catch (_) {}
            reject(new Error(err));
          }
        }
      };
      const fd = new FormData();
      fd.append('file', file);
      xhr.send(fd);
    });
  },
  searchFiles: (q: string, top_k: number = 10, mode: 'vector' | 'filename' = 'vector') =>
    request<{ items: SearchResultItem[]; query: string }>(`/search?q=${encodeURIComponent(q)}&top_k=${top_k}&mode=${mode}`),
};
