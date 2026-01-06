export interface RepoItem {
  key: string;
  name: string;
  version: string;
  author?: string;
  description?: string;
  website?: string;
  github?: string;
  icon?: string;
  supportedExts?: string[];
  createdAt?: number;
  downloads?: number;
  directUrl: string;
}

export interface RepoListResponse {
  items: RepoItem[];
  total: number;
  page: number;
  pageSize: number;
}

export interface RepoQueryParams {
  query?: string;
  author?: string;
  sort?: 'downloads' | 'createdAt';
  page?: number;
  pageSize?: number;
}

// foxel-core 应用中心的数据结构
export interface FoxelCoreApp {
  key: string;
  version: string;
  name: {
    zh: string;
    en: string;
  };
  description: {
    zh: string;
    en: string;
  };
  author: string;
  website: string;
  tags: {
    zh: string[];
    en: string[];
  };
  approvedAt: number;
  detailUrl: string;
  downloadUrl: string;
}

export interface FoxelCoreAppsResponse {
  apps: FoxelCoreApp[];
}

export interface FoxelCoreAppVersion {
  version: string;
  name: {
    zh: string;
    en: string;
  };
  description: {
    zh: string;
    en: string;
  };
  author: string;
  website: string;
  tags: {
    zh: string[];
    en: string[];
  };
  approvedAt: number;
  releaseNotesMd: string | null;
}

export interface FoxelCoreAppDetail {
  key: string;
  latest: FoxelCoreAppVersion & {
    downloadUrl: string;
  };
  versions: FoxelCoreAppVersion[];
}

export interface FoxelCoreAppDetailResponse {
  app: FoxelCoreAppDetail;
}

const CENTER_BASE = 'https://center.foxel.cc';
const FOXEL_CORE_BASE = 'https://foxel.cc';

export function buildCenterUrl(path: string) {
  return new URL(path, CENTER_BASE).href;
}

export async function fetchRepoList(params: RepoQueryParams = {}): Promise<RepoListResponse> {
  const query = new URLSearchParams();
  if (params.query) query.set('query', params.query);
  if (params.author) query.set('author', params.author);
  if (params.sort) query.set('sort', params.sort);
  query.set('page', String(params.page ?? 1));
  query.set('pageSize', String(params.pageSize ?? 12));

  const url = `${CENTER_BASE}/api/repo?${query.toString()}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Repo fetch failed: ${resp.status}`);
  }
  return await resp.json();
}

/**
 * 从 foxel-core 应用中心获取应用列表
 */
export async function fetchFoxelCoreApps(query?: string): Promise<FoxelCoreApp[]> {
  const url = new URL('/api/apps', FOXEL_CORE_BASE);
  const q = query?.trim();
  if (q) {
    url.searchParams.set('q', q);
  }
  const resp = await fetch(url.href);
  if (!resp.ok) {
    throw new Error(`Failed to fetch apps: ${resp.status}`);
  }
  const data: FoxelCoreAppsResponse = await resp.json();
  return data.apps;
}

/**
 * 从 foxel-core 应用中心获取应用详情（含历史版本）
 */
export async function fetchFoxelCoreAppDetail(appKey: string): Promise<FoxelCoreAppDetail> {
  const url = `${FOXEL_CORE_BASE}/api/apps/${encodeURIComponent(appKey)}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Failed to fetch app detail: ${resp.status}`);
  }
  const data: FoxelCoreAppDetailResponse = await resp.json();
  return data.app;
}

/**
 * 从 foxel-core 下载应用包文件
 */
export async function downloadFoxelCoreApp(app: Pick<FoxelCoreApp, 'key' | 'version' | 'downloadUrl'>): Promise<File> {
  const url = `${FOXEL_CORE_BASE}${app.downloadUrl}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Failed to download app: ${resp.status}`);
  }
  const blob = await resp.blob();
  const filename = `${app.key}-${app.version}.foxpkg`;
  return new File([blob], filename, { type: 'application/octet-stream' });
}
