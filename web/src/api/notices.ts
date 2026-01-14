export interface NoticeItem {
  id: number;
  title: string;
  contentMd: string;
  isPopup: boolean;
  createdAt: number;
}

export interface GetNoticesResponse {
  items: NoticeItem[];
  page: number;
  pageSize: number;
  total: number;
}

export interface GetNoticesParams {
  version: string;
  page?: number;
}

const FOXEL_CORE_BASE = 'https://foxel.cc';

function normalizeVersion(version: string) {
  return (version || '').trim().replace(/^v/i, '');
}

function extractErrorMessage(data: any) {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (typeof data.detail === 'string') return data.detail;
  if (typeof data.code === 'string') return data.code;
  if (typeof data.message === 'string') return data.message;
  if (typeof data.msg === 'string') return data.msg;
  return '';
}

export const noticesApi = {
  list: async (params: GetNoticesParams): Promise<GetNoticesResponse> => {
    const url = new URL('/api/notices', FOXEL_CORE_BASE);
    url.searchParams.set('version', normalizeVersion(params.version));
    url.searchParams.set('page', String(params.page ?? 1));

    const resp = await fetch(url.href);
    if (!resp.ok) {
      let msg = resp.statusText || `Request failed: ${resp.status}`;
      try {
        const data = await resp.json();
        msg = extractErrorMessage(data) || msg;
      } catch { void 0; }
      throw new Error(msg);
    }
    return await resp.json();
  },
};

