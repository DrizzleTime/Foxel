import type { VfsEntry } from '../../api/client';

export type { FoxelExternals } from '../externals';

export const HOST_API_VERSION = '1.0.0';
export type PluginCapability = 'monaco' | 'artplayer';
export type PluginCleanup = () => void | Promise<void>;

/**
 * 宿主 API 接口
 */
export interface FoxelHostApi {
  /**
   * 关闭当前插件窗口
   */
  close: () => Promise<void>;

  /**
   * 在文件浏览器中打开指定路径
   */
  openPath?: (path: string) => Promise<void>;

  /**
   * 使用指定应用打开文件
   */
  openFile?: (filePath: string, appKey?: string) => Promise<void>;

  /**
   * 显示消息提示
   */
  showMessage: (type: 'success' | 'error' | 'info' | 'warning', content: string) => void;

  /**
   * 调用 API
   */
  callApi: <T = unknown>(path: string, options?: RequestInit & { json?: unknown }) => Promise<T>;

  /**
   * 获取文件的临时公开链接
   */
  getTempLink?: (filePath: string) => Promise<string>;

  /**
   * 获取文件流式播放/下载 URL
   */
  getStreamUrl?: (filePath: string) => string;
}

/**
 * 插件上下文 - 文件打开模式
 */
export interface PluginContext {
  /** 文件路径 */
  filePath: string;
  /** 文件信息 */
  entry: VfsEntry;
  /** 文件 URL */
  urls: {
    /** 临时下载链接 */
    downloadUrl: string;
    /** 流式播放链接 */
    streamUrl?: string;
  };
  /** 宿主 API */
  host: FoxelHostApi;
}

/**
 * 插件上下文 - 独立应用模式
 */
export interface PluginAppContext {
  /** 宿主 API */
  host: FoxelHostApi;
}

/**
 * 已注册的插件接口
 */
export interface RegisteredPlugin {
  /**
   * 挂载插件（文件打开模式）
   * @returns 可选的清理函数
   */
  mount: (container: HTMLElement, ctx: PluginContext) => void | PluginCleanup | Promise<void | PluginCleanup>;

  /**
   * 卸载插件（文件打开模式）
   */
  unmount?: (container: HTMLElement) => void | Promise<void>;

  /**
   * 挂载独立应用
   * @returns 可选的清理函数
   */
  mountApp?: (container: HTMLElement, ctx: PluginAppContext) => void | PluginCleanup | Promise<void | PluginCleanup>;

  /**
   * 卸载独立应用
   */
  unmountApp?: (container: HTMLElement) => void | Promise<void>;
}

