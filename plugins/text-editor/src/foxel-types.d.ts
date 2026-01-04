/**
 * Foxel 核心类型定义（宿主接口）
 * - 本文件在所有插件中保持一致
 */

declare global {
  interface Window {
    __FOXEL_EXTERNALS__: {
      React: typeof import('react');
      ReactDOM: typeof import('react-dom/client');
      antd: typeof import('antd');
      AntdIcons: typeof import('@ant-design/icons');
      foxelApi: FoxelApi;
      version: string;
    };
    __FOXEL_LAST_EXPLORER_PAGE__?: ExplorerSnapshot;
    __FOXEL_SYSTEM_STATUS__?: {
      file_domain?: string;
    };
    FoxelRegister: (plugin: PluginRegistration) => void;
  }
}

export interface VfsEntry {
  name: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  type?: string;
  has_thumbnail?: boolean;
  path?: string;
}

export interface ExifData {
  [key: string]: string | number | undefined;
}

export interface TempLinkResponse {
  token: string;
  path: string;
  url: string;
}

export interface FileStat extends VfsEntry {
  mode?: number;
  exif?: ExifData | null;
  vector_index?: unknown;
}

export interface HostApi {
  close: () => void;
  openPath?: (path: string) => void;
  openFile?: (filePath: string, appKey?: string) => void;
  showMessage: (type: 'success' | 'error' | 'info' | 'warning', content: string) => void;
  callApi: <T = unknown>(path: string, options?: RequestInit & { json?: unknown }) => Promise<T>;
  getTempLink?: (path: string) => Promise<string>;
  getStreamUrl?: (path: string) => string;
}

export interface AppContext {
  host: HostApi;
}

export interface PluginContext {
  filePath: string;
  entry: VfsEntry;
  urls: {
    downloadUrl: string;
    streamUrl: string;
  };
  host: HostApi;
}

export interface PluginRegistration {
  mount?: (container: HTMLElement, ctx: PluginContext) => (() => void) | void;
  mountApp?: (container: HTMLElement, ctx: AppContext) => (() => void) | void;
}

export interface RequestOptions extends RequestInit {
  json?: unknown;
  formData?: FormData;
  text?: string;
  rawResponse?: boolean;
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

export interface VfsCopyMoveResult {
  src: string;
  dst: string;
  overwrite: boolean;
  copied?: boolean;
  moved?: boolean;
  queued?: boolean;
  task_id?: string;
  task_name?: string;
}

export interface FoxelApi {
  baseUrl: string;
  request: <T = any>(path: string, options?: RequestOptions) => Promise<T>;
  vfs: {
    list: (
      path: string,
      page?: number,
      pageSize?: number,
      sortBy?: string,
      sortOrder?: string
    ) => Promise<DirListing>;
    stat: (path: string) => Promise<FileStat>;
    mkdir: (path: string) => Promise<{ created: boolean; path: string }>;
    rename: (src: string, dst: string) => Promise<{ renamed: boolean; src: string; dst: string; overwrite: boolean }>;
    deletePath: (path: string) => Promise<{ deleted: boolean; path: string }>;
    copy: (src: string, dst: string, options?: { overwrite?: boolean }) => Promise<VfsCopyMoveResult>;
    move: (src: string, dst: string, options?: { overwrite?: boolean }) => Promise<VfsCopyMoveResult>;
    streamUrl: (path: string) => string;
    getTempLinkToken: (path: string, expiresIn?: number) => Promise<TempLinkResponse>;
    getTempPublicUrl: (token: string) => string;
    readFile: (path: string) => Promise<ArrayBuffer>;
    uploadFile: (path: string, file: File | Blob) => Promise<{ written: boolean; path: string; size: number }>;
  };
  plugins: {
    list: () => Promise<any>;
    get: (key: string) => Promise<any>;
    install: (file: File) => Promise<any>;
    remove: (key: string) => Promise<any>;
    getBundleUrl: (key: string) => string;
    getAssetUrl: (key: string, assetPath: string) => string;
  };
}

export interface ExplorerSnapshot {
  path: string;
  entries: VfsEntry[];
  pagination?: {
    total: number;
    page: number;
    page_size: number;
    pages: number;
  };
  sortBy: string;
  sortOrder: string;
  timestamp: number;
}
