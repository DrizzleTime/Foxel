/**
 * 插件外部依赖注入模块
 *
 * 宿主应用通过 window.__FOXEL_EXTERNALS__ 暴露共享依赖给插件使用
 * 插件开发时可以直接从 window.__FOXEL_EXTERNALS__ 获取 React、Antd 等依赖
 */

import * as React from 'react';
import * as ReactDOM from 'react-dom/client';
import * as antd from 'antd';
import * as AntdIcons from '@ant-design/icons';

// 代码编辑器（懒加载包装）
// 编辑器组件已移除，由插件自己提供

// API 模块
import request, { vfsApi, API_BASE_URL } from '../api/client';
import { pluginsApi } from '../api/plugins';

// 类型定义
import type { VfsEntry, DirListing } from '../api/client';
import type { PluginItem } from '../api/plugins';

type Lang = 'zh' | 'en';
type Dict = Record<string, string>;
type Dicts = Partial<Record<Lang, Dict>>;

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => String(params[k] ?? `{${k}}`));
}

/**
 * 宿主 API 接口
 */
export interface FoxelHostApi {
  /**
   * 关闭当前插件窗口
   */
  close: () => void;

  /**
   * 在文件浏览器中打开指定路径
   */
  openPath?: (path: string) => void;

  /**
   * 使用指定应用打开文件
   */
  openFile?: (filePath: string, appKey?: string) => void;

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
  mount: (container: HTMLElement, ctx: PluginContext) => void | (() => void) | Promise<void | (() => void)>;

  /**
   * 卸载插件（文件打开模式）
   */
  unmount?: (container: HTMLElement) => void | Promise<void>;

  /**
   * 挂载独立应用
   * @returns 可选的清理函数
   */
  mountApp?: (container: HTMLElement, ctx: PluginAppContext) => void | (() => void) | Promise<void | (() => void)>;

  /**
   * 卸载独立应用
   */
  unmountApp?: (container: HTMLElement) => void | Promise<void>;
}

/**
 * VFS API 包装
 */
const vfsApiWrapper = {
  list: vfsApi.list,
  stat: vfsApi.stat,
  mkdir: vfsApi.mkdir,
  rename: vfsApi.rename,
  deletePath: vfsApi.deletePath,
  copy: vfsApi.copy,
  move: vfsApi.move,
  streamUrl: vfsApi.streamUrl,
  getTempLinkToken: vfsApi.getTempLinkToken,
  getTempPublicUrl: vfsApi.getTempPublicUrl,
  readFile: vfsApi.readFile,
  uploadFile: vfsApi.uploadFile,
};

/**
 * 暴露给插件的外部依赖
 */
export interface FoxelExternals {
  // React 核心
  React: typeof React;
  ReactDOM: typeof ReactDOM;

  // UI 库
  antd: typeof antd;
  AntdIcons: typeof AntdIcons;

  // i18n
  i18n?: {
    getLang: () => Lang;
    subscribe: (cb: (lang: Lang) => void) => () => void;
    create: (dicts: Dicts) => {
      t: (key: string, params?: Record<string, string | number>) => string;
      useI18n: () => { lang: Lang; t: (key: string, params?: Record<string, string | number>) => string };
    };
  };

  // Foxel API
  foxelApi: {
    /** HTTP 请求函数 */
    request: typeof request;
    /** VFS 文件系统 API */
    vfs: typeof vfsApiWrapper;
    /** 插件管理 API */
    plugins: typeof pluginsApi;
    /** API 基础 URL */
    baseUrl: string;
  };

  // 版本信息
  version: string;
}

// 声明全局类型
declare global {
  interface Window {
    __FOXEL_EXTERNALS__?: FoxelExternals;
    FoxelRegister?: (plugin: RegisteredPlugin) => void;
  }
}

/**
 * 初始化并暴露外部依赖
 */
export function initExternals(): void {
  const normalizeLang = (raw: unknown): Lang => (raw === 'en' ? 'en' : 'zh');

  const i18nApi = {
    getLang: () => normalizeLang(localStorage.getItem('lang')),
    subscribe: (cb: (lang: Lang) => void) => {
      const handler = (e: Event) => {
        const lang = (e as CustomEvent)?.detail?.lang as Lang;
        cb(normalizeLang(lang));
      };
      window.addEventListener('foxel:langchange', handler as any);
      return () => window.removeEventListener('foxel:langchange', handler as any);
    },
    create: (dicts: Dicts) => {
      const t = (key: string, params?: Record<string, string | number>) => {
        const lang = i18nApi.getLang();
        const dict = dicts[lang] || {};
        return interpolate(dict[key] ?? key, params);
      };

      const useI18n = () => {
        const [lang, setLang] = React.useState<Lang>(() => i18nApi.getLang());
        React.useEffect(() => i18nApi.subscribe(setLang), []);
        const tt = React.useCallback((key: string, params?: Record<string, string | number>) => {
          const dict = dicts[lang] || {};
          return interpolate(dict[key] ?? key, params);
        }, [lang]);
        return { lang, t: tt };
      };

      return { t, useI18n };
    },
  };

  if (window.__FOXEL_EXTERNALS__) {
    window.__FOXEL_EXTERNALS__.i18n = i18nApi;
    return; // 已初始化
  }

  window.__FOXEL_EXTERNALS__ = {
    // React 核心
    React,
    ReactDOM,

    // UI 库
    antd,
    AntdIcons,

    // i18n
    i18n: i18nApi,

    // Foxel API
    foxelApi: {
      request,
      vfs: vfsApiWrapper,
      plugins: pluginsApi,
      baseUrl: API_BASE_URL,
    },

    // 版本信息
    version: '1.0.0',
  };

  console.debug('[Foxel] Plugin externals initialized');
}

/**
 * 获取外部依赖
 */
export function getExternals(): FoxelExternals | undefined {
  return window.__FOXEL_EXTERNALS__;
}

// 导出类型供插件 SDK 使用
export type { VfsEntry, DirListing, PluginItem };
